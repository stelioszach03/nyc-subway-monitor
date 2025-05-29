
"""
Pydantic schemas for anomaly detection results.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AnomalyBase(BaseModel):
    """Base anomaly detection result."""
    
    station_id: Optional[str] = None
    line: Optional[str] = None
    anomaly_type: str = Field(..., description="Type of anomaly detected")
    severity: float = Field(..., ge=0, le=1, description="Anomaly severity score")
    model_name: str
    model_version: str
    features: Dict[str, float] = Field(default_factory=dict)
    meta_data: Dict[str, Any] = Field(default_factory=dict)  # Fixed: any -> Any


class AnomalyCreate(AnomalyBase):
    """Schema for creating new anomaly records."""
    pass


class AnomalyResponse(AnomalyBase):
    """Anomaly response with full details."""
    
    id: int
    detected_at: datetime
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AnomalyListResponse(BaseModel):
    """Paginated anomaly list."""
    
    anomalies: List[AnomalyResponse]
    total: int
    page: int
    page_size: int
    

class AnomalyStats(BaseModel):
    """Anomaly statistics for dashboard."""
    
    total_today: int
    total_active: int
    by_type: Dict[str, int]
    by_line: Dict[str, int]
    severity_distribution: Dict[str, int]  # low/medium/high counts
    trend_24h: List[Dict[str, Any]]  # Fixed: any -> Any


class WebSocketMessage(BaseModel):
    """WebSocket message format for real-time updates."""
    
    type: str = Field(..., description="Message type: anomaly|heartbeat|stats")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    data: Optional[Dict[str, Any]] = None  # Fixed: any -> Any