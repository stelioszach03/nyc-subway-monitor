# --- backend/app/db/database.py ---
"""
Database connection and session management using SQLAlchemy with asyncpg.
Includes TimescaleDB hypertable setup for time-series data.
"""

from typing import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Create async engine with proper isolation level for concurrent operations
engine = create_async_engine(
    str(settings.database_url),
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    isolation_level="READ COMMITTED",  # Prevent serialization errors
    pool_recycle=3600,  # Recycle connections after 1 hour
    pool_timeout=30,    # Timeout for getting connection from pool
)

# Async session factory with autoflush disabled to prevent premature flushes
AsyncSessionLocal = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False,
    autoflush=False,  # Disable autoflush to control when flushes happen
)

# Declarative base for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            # Don't auto-commit here, let the endpoint handle it
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database with TimescaleDB extensions and hypertables."""
    try:
        async with engine.begin() as conn:
            # Create TimescaleDB extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            
            # Drop foreign key constraints before dropping tables in debug mode
            if settings.debug:
                logger.info("Dropping foreign key constraints for clean demo setup")
                await conn.execute(text("""
                    DO $$
                    DECLARE
                        r RECORD;
                    BEGIN
                        FOR r IN (
                            SELECT conname, conrelid::regclass AS table_name
                            FROM pg_constraint
                            WHERE contype = 'f'
                            AND connamespace = 'public'::regnamespace
                        ) LOOP
                            EXECUTE 'ALTER TABLE ' || r.table_name || ' DROP CONSTRAINT IF EXISTS ' || r.conname || ' CASCADE';
                        END LOOP;
                    END $$;
                """))
                
                logger.info("Dropping existing tables for clean demo setup")
                await conn.run_sync(Base.metadata.drop_all)
            
            # Create tables
            await conn.run_sync(Base.metadata.create_all)
            
        # Create hypertables in separate transactions
        await create_hypertables()
        
        # Create additional indexes
        await create_indexes()
        
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise


async def create_hypertables() -> None:
    """Create TimescaleDB hypertables."""
    hypertables = [
        ("feed_updates", "timestamp"),
        ("anomalies", "detected_at"),
        ("train_positions", "timestamp"),
    ]
    
    for table_name, time_column in hypertables:
        try:
            async with engine.begin() as conn:
                # Check if table is already a hypertable
                result = await conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM timescaledb_information.hypertables
                        WHERE hypertable_name = :table_name
                    """),
                    {"table_name": table_name}
                )
                count = result.scalar()
                
                if count == 0:
                    # Create hypertable
                    await conn.execute(
                        text(f"""
                            SELECT create_hypertable(
                                '{table_name}',
                                '{time_column}',
                                chunk_time_interval => INTERVAL '1 day',
                                create_default_indexes => FALSE,
                                if_not_exists => TRUE
                            )
                        """)
                    )
                    logger.info(f"Created hypertable for {table_name}")
                else:
                    logger.info(f"Hypertable {table_name} already exists")
                    
        except Exception as e:
            logger.warning(f"Could not create hypertable {table_name}", error=str(e))


async def create_indexes() -> None:
    """Create additional indexes for common queries."""
    # TimescaleDB doesn't support CONCURRENTLY on hypertables
    # Remove CONCURRENTLY for hypertable indexes
    indexes = [
        # Foreign key indexes to prevent deadlocks
        "CREATE INDEX IF NOT EXISTS idx_train_positions_current_station ON train_positions(current_station)",
        "CREATE INDEX IF NOT EXISTS idx_train_positions_next_station ON train_positions(next_station)",
        
        # Query performance indexes
        "CREATE INDEX IF NOT EXISTS idx_anomalies_station_time ON anomalies(station_id, detected_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_train_positions_line_time ON train_positions(line, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_feed_updates_feed_time ON feed_updates(feed_id, timestamp DESC)",
        
        # Station lookup index (regular table, can use CONCURRENTLY)
        "CREATE INDEX IF NOT EXISTS idx_stations_id ON stations(id)",
    ]
    
    for index_sql in indexes:
        try:
            # For hypertables, we need to create indexes in a separate transaction
            async with engine.connect() as conn:
                await conn.execute(text("COMMIT"))  # End any existing transaction
                await conn.execute(text(index_sql))
                await conn.commit()
                logger.info(f"Created index: {index_sql.split('idx_')[1].split(' ')[0]}")
        except Exception as e:
            logger.warning(f"Could not create index", sql=index_sql, error=str(e))