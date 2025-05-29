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

# Create async engine
engine = create_async_engine(
    str(settings.database_url),
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
)

# Async session factory
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Declarative base for models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency to get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database with TimescaleDB extensions and hypertables."""
    async with engine.begin() as conn:
        # Create TimescaleDB extension
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE"))
        
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        
        # Convert time-series tables to hypertables
        hypertables = [
            ("feed_updates", "timestamp"),
            ("anomalies", "detected_at"),
            ("train_positions", "timestamp"),
        ]
        
        for table_name, time_column in hypertables:
            try:
                await conn.execute(
                    text(f"""
                        SELECT create_hypertable(
                            '{table_name}',
                            '{time_column}',
                            if_not_exists => TRUE,
                            chunk_time_interval => INTERVAL '1 day'
                        )
                    """)
                )
                logger.info(f"Created hypertable for {table_name}")
            except Exception as e:
                logger.warning(f"Hypertable {table_name} may already exist", error=str(e))
        
        # Create indexes for common queries
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_anomalies_station_time ON anomalies(station_id, detected_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_train_positions_line_time ON train_positions(line, timestamp DESC)",
            "CREATE INDEX IF NOT EXISTS idx_feed_updates_line ON feed_updates(feed_id, timestamp DESC)",
        ]
        
        for index_sql in indexes:
            await conn.execute(text(index_sql))
        
        logger.info("Database initialized successfully")