"""
Pydantic schemas for GTFS-RT feed data validation and serialization.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class StationBase(BaseModel):
    """Base station information."""
    
    id: str = Field(..., description="GTFS stop_id")
    name: str
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    lines: List[str] = Field(default_factory=list)
    borough: Optional[str] = None


class TrainPositionBase(BaseModel):
    """Real-time train position data."""
    
    trip_id: str
    route_id: str
    line: str
    direction: int = Field(..., ge=0, le=1)
    current_station: Optional[str] = None
    next_station: Optional[str] = None
    arrival_time: Optional[datetime] = None
    departure_time: Optional[datetime] = None
    delay_seconds: int = 0
    
    # Computed features
    headway_seconds: Optional[int] = None
    dwell_time_seconds: Optional[int] = None
    schedule_adherence: Optional[float] = None
    
    @field_validator("delay_seconds")
    def validate_delay(cls, v: int) -> int:
        """Cap extreme delays at ±30 minutes."""
        return max(-1800, min(1800, v))


class FeedUpdateResponse(BaseModel):
    """Response for feed update status."""
    
    timestamp: datetime
    feed_id: str
    num_trips: int
    num_alerts: int
    processing_time_ms: float
    status: str = "success"
    
    class Config:
        from_attributes = True


class TrainPositionResponse(TrainPositionBase):
    """Train position with additional metadata."""
    
    id: int
    timestamp: datetime
    
    class Config:
        from_attributes = True