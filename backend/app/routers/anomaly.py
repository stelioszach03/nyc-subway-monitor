"""
Fixed anomaly detection endpoints with proper error handling.
"""

from datetime import datetime, timedelta
from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import crud
from app.db.database import get_db
from app.ml.predict import AnomalyDetector
from app.routers.websocket import broadcast_anomaly
from app.schemas.anomaly import (
    AnomalyListResponse,
    AnomalyResponse,
    AnomalyStats,
)

logger = structlog.get_logger()
router = APIRouter()


@router.get("/", response_model=AnomalyListResponse)
async def list_anomalies(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    line: Optional[str] = None,
    station_id: Optional[str] = None,
    resolved: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> AnomalyListResponse:
    """Get paginated list of anomalies with filters."""
    
    # Default date range if not specified
    if not start_date:
        start_date = datetime.utcnow() - timedelta(days=1)
    if not end_date:
        end_date = datetime.utcnow()
    
    try:
        anomalies, total = await crud.get_anomalies(
            db,
            page=page,
            page_size=page_size,
            line=line,
            station_id=station_id,
            resolved=resolved,
            start_date=start_date,
            end_date=end_date,
        )
        
        return AnomalyListResponse(
            anomalies=[AnomalyResponse.from_orm(a) for a in anomalies],
            total=total,
            page=page,
            page_size=page_size,
        )
        
    except Exception as e:
        logger.error(f"Failed to list anomalies: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve anomalies"
        )


@router.get("/stats", response_model=AnomalyStats)
async def get_anomaly_stats(
    db: AsyncSession = Depends(get_db),
    hours: int = Query(24, ge=1, le=168),
) -> AnomalyStats:
    """Get anomaly statistics for dashboard."""
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    
    try:
        stats = await crud.get_anomaly_stats(db, start_time, end_time)
        trend = await crud.get_anomaly_trend(db, start_time, end_time)
        
        return AnomalyStats(
            total_today=stats["total_today"],
            total_active=stats["total_active"],
            by_type=stats["by_type"],
            by_line=stats["by_line"],
            severity_distribution=stats["severity_distribution"],
            trend_24h=trend,
        )
        
    except Exception as e:
        logger.error(f"Failed to get anomaly stats: {e}")
        # Return empty stats instead of failing
        return AnomalyStats(
            total_today=0,
            total_active=0,
            by_type={},
            by_line={},
            severity_distribution={"low": 0, "medium": 0, "high": 0},
            trend_24h=[],
        )


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
async def get_anomaly(
    anomaly_id: int,
    db: AsyncSession = Depends(get_db),
) -> AnomalyResponse:
    """Get single anomaly details."""
    anomaly = await crud.get_anomaly_by_id(db, anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    
    return AnomalyResponse.from_orm(anomaly)


@router.post("/{anomaly_id}/resolve")
async def resolve_anomaly(
    anomaly_id: int,
    db: AsyncSession = Depends(get_db),
) -> AnomalyResponse:
    """Mark anomaly as resolved."""
    anomaly = await crud.resolve_anomaly(db, anomaly_id)
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    
    await db.commit()
    
    return AnomalyResponse.from_orm(anomaly)


@router.post("/detect")
async def run_detection(
    request: Request,
    db: AsyncSession = Depends(get_db),
    line: Optional[str] = None,
    lookback_minutes: int = Query(60, ge=10, le=360),
) -> dict:
    """Manually trigger anomaly detection."""
    
    # Get detector from app state
    if not hasattr(request.app.state, 'detector'):
        raise HTTPException(
            status_code=503,
            detail="Anomaly detector not initialized"
        )
    
    detector: AnomalyDetector = request.app.state.detector
    
    start_time = datetime.utcnow() - timedelta(minutes=lookback_minutes)
    
    # Get recent train positions
    positions = await crud.get_train_positions_since(
        db, start_time, line=line
    )
    
    if not positions:
        return {
            "message": "No recent data to analyze",
            "positions_checked": 0,
            "anomalies_detected": 0,
        }
    
    # Run detection
    try:
        anomalies = await detector.detect_anomalies(positions)
    except Exception as e:
        logger.error(f"Detection failed: {e}")
        raise HTTPException(
            status_code=500,
            detail="Anomaly detection failed"
        )
    
    # Save detected anomalies
    saved_anomalies = []
    for anomaly_data in anomalies:
        try:
            anomaly = await crud.create_anomaly(db, anomaly_data)
            saved_anomalies.append(anomaly)
            
            # Broadcast via WebSocket
            await broadcast_anomaly(anomaly_data)
            
        except Exception as e:
            logger.error(f"Failed to save anomaly: {e}")
    
    await db.commit()
    
    return {
        "message": "Detection complete",
        "positions_checked": len(positions),
        "anomalies_detected": len(saved_anomalies),
        "anomalies": [AnomalyResponse.from_orm(a) for a in saved_anomalies],
    }


@router.get("/models/status")
async def get_model_status(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Get status of deployed ML models."""
    
    models = await crud.get_active_models(db)
    
    # Check if detector is available
    detector_stats = {}
    if hasattr(request.app.state, 'detector'):
        detector: AnomalyDetector = request.app.state.detector
        detector_stats = detector.get_model_stats()
    
    return {
        "models": [
            {
                "type": model.model_type,
                "version": model.version,
                "trained_at": model.trained_at,
                "metrics": model.metrics,
                "is_loaded": detector_stats.get("loaded_models", {}).get(model.model_type, False),
            }
            for model in models
        ],
        "detector_stats": detector_stats,
    }