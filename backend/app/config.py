"""
Application configuration using Pydantic Settings for type safety and validation.
Loads from environment variables with sensible defaults for development.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for NYC Subway Monitor."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
    
    # Application
    app_name: str = "NYC Subway Monitor"
    app_version: str = "1.0.0"
    debug: bool = Field(default=False, description="Enable debug mode")
    
    # API
    api_v1_prefix: str = "/api/v1"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3001"]
    
    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    postgres_db: str = "subway_monitor"
    
    # Computed database URL
    database_url: Optional[PostgresDsn] = None
    
    @field_validator("database_url", mode="before")
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=info.data.get("postgres_user"),
            password=info.data.get("postgres_password"),
            host=info.data.get("postgres_host"),
            port=info.data.get("postgres_port"),
            path=info.data.get("postgres_db"),
        )
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # ML Configuration
    model_retrain_hour: int = Field(default=3, ge=0, le=23)
    anomaly_contamination: float = Field(default=0.05, ge=0.01, le=0.2)
    lstm_sequence_length: int = Field(default=24, ge=1)
    lstm_hidden_size: int = Field(default=128, ge=16)
    
    # Feed Configuration
    feed_update_interval: int = Field(default=30, ge=10, description="Seconds between feed updates")
    feed_timeout: int = Field(default=10, ge=5)
    max_retries: int = Field(default=3, ge=1)
    
    # Feature Engineering
    headway_window_minutes: int = Field(default=30, ge=10)
    rolling_window_hours: int = Field(default=1, ge=1)
    
    # WebSocket
    ws_heartbeat_interval: int = Field(default=30, ge=10)
    ws_max_connections: int = Field(default=1000, ge=10)


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance to avoid repeated parsing."""
    return Settings()