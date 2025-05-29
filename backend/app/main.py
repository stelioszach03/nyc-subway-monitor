# --- backend/app/main.py ---
"""
FastAPI application entry point for NYC Subway Monitor.
Configures middleware, routers, and lifecycle events.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.core.exceptions import SubwayMonitorException
from app.db.database import init_db
from app.ml.train import ModelTrainer
from app.ml.predict import AnomalyDetector
from app.routers import anomaly, feed, health, websocket

logger = structlog.get_logger()
settings = get_settings()

# Global instances
model_trainer = ModelTrainer()
anomaly_detector = AnomalyDetector()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle manager."""
    # Startup
    logger.info("Starting NYC Subway Monitor", version=settings.app_version)
    
    try:
        # Initialize database
        await init_db()
        
        # Load ML models
        await model_trainer.load_or_train_models()
        
        # Register models with detector
        for model_type, model in model_trainer.active_models.items():
            anomaly_detector.register_model(model_type, model)
        
        # Store references in app state
        app.state.trainer = model_trainer
        app.state.detector = anomaly_detector
        
        # Start background tasks
        app.state.feed_task = asyncio.create_task(feed.start_feed_ingestion())
        
        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error("Failed to start application", error=str(e))
        # Continue anyway for development
        if not settings.debug:
            raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down NYC Subway Monitor")
    if hasattr(app.state, 'feed_task'):
        app.state.feed_task.cancel()
        try:
            await app.state.feed_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
@app.exception_handler(SubwayMonitorException)
async def subway_monitor_exception_handler(request, exc: SubwayMonitorException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )

# Mount routers
app.include_router(health.router, tags=["health"])
app.include_router(feed.router, prefix=f"{settings.api_v1_prefix}/feeds", tags=["feeds"])
app.include_router(anomaly.router, prefix=f"{settings.api_v1_prefix}/anomalies", tags=["anomalies"])
app.include_router(websocket.router, prefix=f"{settings.api_v1_prefix}/ws", tags=["websocket"])

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Root redirect
@app.get("/")
async def root():
    """Redirect to API documentation."""
    return {"message": "NYC Subway Monitor API", "docs": f"{settings.api_v1_prefix}/docs"}

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["default"],
            },
        },
    )