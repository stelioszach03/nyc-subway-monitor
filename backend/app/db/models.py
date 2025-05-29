
"""
SQLAlchemy models for NYC Subway Monitor.
Designed for TimescaleDB with proper time-series optimization.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.database import Base


class Station(Base):
    """Static station information."""
    
    __tablename__ = "stations"
    
    id = Column(String(10), primary_key=True)  # GTFS stop_id
    name = Column(String(255), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    lines = Column(JSONB, default=list)  # ["4", "5", "6"]
    borough = Column(String(50))
    
    # Relationships
    anomalies = relationship("Anomaly", back_populates="station")
    

class FeedUpdate(Base):
    """Raw GTFS-RT feed data with parsed features."""
    
    __tablename__ = "feed_updates"
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    feed_id = Column(String(20), nullable=False)  # "ace", "bdfm", etc.
    raw_data = Column(JSONB)  # Decoded protobuf as JSON
    num_trips = Column(Integer)
    num_alerts = Column(Integer)
    processing_time_ms = Column(Float)
    
    __table_args__ = (
        Index("idx_feed_timestamp", "feed_id", "timestamp"),
    )


class TrainPosition(Base):
    """Real-time train positions and predictions."""
    
    __tablename__ = "train_positions"
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    trip_id = Column(String(100), nullable=False)
    route_id = Column(String(10), nullable=False)  # "6", "L", etc.
    line = Column(String(20), nullable=False)  # Line grouping
    direction = Column(Integer)  # 0=South/West, 1=North/East
    current_station = Column(String(10), ForeignKey("stations.id"))
    next_station = Column(String(10), ForeignKey("stations.id"))
    arrival_time = Column(DateTime(timezone=True))
    departure_time = Column(DateTime(timezone=True))
    delay_seconds = Column(Integer, default=0)
    
    # Computed features
    headway_seconds = Column(Integer)  # Time since previous train
    dwell_time_seconds = Column(Integer)  # Stop duration
    schedule_adherence = Column(Float)  # Z-score of delay
    
    __table_args__ = (
        Index("idx_train_line_time", "line", "timestamp"),
        Index("idx_train_station", "current_station", "timestamp"),
    )


class Anomaly(Base):
    """Detected anomalies from ML models."""
    
    __tablename__ = "anomalies"
    
    id = Column(Integer, primary_key=True)
    detected_at = Column(DateTime(timezone=True), nullable=False, default=func.now(), index=True)
    station_id = Column(String(10), ForeignKey("stations.id"))
    line = Column(String(20))
    anomaly_type = Column(String(50))  # "headway", "dwell", "delay", "combined"
    severity = Column(Float)  # 0-1 score
    model_name = Column(String(50))  # "isolation_forest", "lstm"
    model_version = Column(String(100))
    
    # Context
    features = Column(JSONB)  # Input features that triggered anomaly
    meta_data = Column(JSONB)  # Additional context (renamed from metadata)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime(timezone=True))
    
    # Relationships
    station = relationship("Station", back_populates="anomalies")
    
    __table_args__ = (
        Index("idx_anomaly_active", "resolved", "detected_at"),
        Index("idx_anomaly_station_time", "station_id", "detected_at"),
    )


class ModelArtifact(Base):
    """Trained model metadata and paths."""
    
    __tablename__ = "model_artifacts"
    
    id = Column(Integer, primary_key=True)
    model_type = Column(String(50), nullable=False)  # "isolation_forest", "lstm"
    version = Column(String(100), unique=True, nullable=False)
    trained_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    git_sha = Column(String(40))
    
    # Performance metrics
    metrics = Column(JSONB)  # {"precision": 0.85, "recall": 0.78, ...}
    hyperparameters = Column(JSONB)
    training_samples = Column(Integer)
    
    # Storage
    artifact_path = Column(String(500))  # S3 or local path
    is_active = Column(Boolean, default=False)  # Currently deployed model
    
    __table_args__ = (
        UniqueConstraint("model_type", "is_active", name="uq_one_active_per_type"),
    )