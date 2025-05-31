"""
Stations API endpoints.
"""

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.database import get_db
from app.schemas.stations import StationResponse

logger = structlog.get_logger()
router = APIRouter()


@router.get("/", response_model=List[StationResponse])
async def list_stations(
    db: AsyncSession = Depends(get_db),
    line: Optional[str] = None,
    borough: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=2000),
) -> List[StationResponse]:
    """Get list of subway stations with optional filters."""
    
    try:
        stations = await crud.get_stations(
            db,
            line=line,
            borough=borough,
            limit=limit,
        )
        
        return [StationResponse.from_orm(station) for station in stations]
        
    except Exception as e:
        logger.error(f"Failed to list stations: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve stations"
        )


@router.get("/{station_id}", response_model=StationResponse)
async def get_station(
    station_id: str,
    db: AsyncSession = Depends(get_db),
) -> StationResponse:
    """Get single station details."""
    station = await crud.get_station_by_id(db, station_id)
    if not station:
        raise HTTPException(status_code=404, detail="Station not found")
    
    return StationResponse.from_orm(station)