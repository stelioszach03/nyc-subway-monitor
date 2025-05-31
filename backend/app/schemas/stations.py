"""
Station data schemas.
"""

from typing import List, Optional

from pydantic import BaseModel


class StationResponse(BaseModel):
    """Station response schema."""
    
    id: str
    name: str
    lat: float
    lon: float
    lines: Optional[List[str]] = None
    borough: Optional[str] = None
    
    class Config:
        from_attributes = True
        
    @classmethod
    def from_orm(cls, obj):
        """Convert from SQLAlchemy model."""
        lines = obj.lines if isinstance(obj.lines, list) else []
        return cls(
            id=obj.id,
            name=obj.name,
            lat=obj.lat,
            lon=obj.lon,
            lines=lines,
            borough=obj.borough,
        )