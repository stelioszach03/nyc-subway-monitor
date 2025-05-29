"""
Health check endpoints for monitoring and orchestration.
"""

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import get_db

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


@router.get("/health/live")
async def liveness_check():
    """Basic liveness check - is the process running?"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow(),
        "service": settings.app_name,
        "version": settings.app_version,
    }


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Readiness check - can we serve traffic?"""
    checks = {
        "database": False,
        "models_loaded": False,
    }
    
    # Check database connection
    try:
        result = await db.execute(text("SELECT 1"))
        checks["database"] = result.scalar() == 1
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    # Check if ML models are loaded
    # This would check the global model state
    checks["models_loaded"] = True  # Placeholder
    
    # Overall status
    all_healthy = all(checks.values())
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "timestamp": datetime.utcnow(),
        "checks": checks,
    }


@router.get("/health/startup")
async def startup_check():
    """Detailed startup probe for debugging."""
    return {
        "status": "started",
        "timestamp": datetime.utcnow(),
        "config": {
            "debug": settings.debug,
            "feed_count": 9,
            "update_interval": settings.feed_update_interval,
            "ml_models": ["isolation_forest", "lstm_autoencoder"],
        },
    }