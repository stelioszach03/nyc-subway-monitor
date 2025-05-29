"""
Fixed database configuration with proper transaction management.
"""

from typing import AsyncGenerator

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import get_settings

logger = structlog.get_logger()
settings = get_settings()

# Create async engine with proper settings
engine = create_async_engine(
    str(settings.database_url),
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    isolation_level="READ COMMITTED",
    pool_recycle=3600,
    pool_timeout=30,
    connect_args={
        "server_settings": {
            "jit": "off",
            "application_name": "nyc_subway_monitor"
        },
        "command_timeout": 60,
    }
)

# Session factory with proper configuration
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,  # Prevent automatic flushes
    autocommit=False,
)

Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session with proper cleanup."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database with extensions and tables."""
    try:
        async with engine.begin() as conn:
            # Create TimescaleDB extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
            
            # Create tables
            await conn.run_sync(Base.metadata.create_all)
        
        # Create hypertables
        await create_hypertables()
        
        # Create indexes
        await create_indexes()
        
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
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
                # Check if already hypertable
                result = await conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM timescaledb_information.hypertables
                        WHERE hypertable_name = :table_name
                    """),
                    {"table_name": table_name}
                )
                
                if result.scalar() == 0:
                    await conn.execute(
                        text(f"""
                            SELECT create_hypertable(
                                '{table_name}',
                                '{time_column}',
                                chunk_time_interval => INTERVAL '1 day',
                                if_not_exists => TRUE
                            )
                        """)
                    )
                    logger.info(f"Created hypertable: {table_name}")
                    
        except Exception as e:
            logger.warning(f"Hypertable creation failed for {table_name}: {e}")


async def create_indexes() -> None:
    """Create performance indexes."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_train_positions_current_station ON train_positions(current_station)",
        "CREATE INDEX IF NOT EXISTS idx_train_positions_next_station ON train_positions(next_station)",
        "CREATE INDEX IF NOT EXISTS idx_anomalies_station_time ON anomalies(station_id, detected_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_train_positions_line_time ON train_positions(line, timestamp DESC)",
        "CREATE INDEX IF NOT EXISTS idx_feed_updates_feed_time ON feed_updates(feed_id, timestamp DESC)",
    ]
    
    for index_sql in indexes:
        try:
            async with engine.connect() as conn:
                await conn.execute(text(index_sql))
                await conn.commit()
        except Exception as e:
            logger.warning(f"Index creation failed: {e}")
