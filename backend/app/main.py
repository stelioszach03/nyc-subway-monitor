"""
FastAPI application entry point with all fixes integrated.
"""

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.config import get_settings
from app.core.exceptions import SubwayMonitorException
from app.db.database import init_db
# ML imports are optional for minimal setup
try:
    from app.ml.train import ModelTrainer
    from app.ml.predict import AnomalyDetector
    ML_AVAILABLE = True
except ImportError as e:
    print(f"Warning: ML modules not available - {e}")
    ModelTrainer = None
    AnomalyDetector = None
    ML_AVAILABLE = False
from app.routers import anomaly, feed, health, stations, websocket

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifecycle manager with proper initialization."""
    logger.info("Starting NYC Subway Monitor", version=settings.app_version)
    
    try:
        # Initialize database with retries
        for attempt in range(3):
            try:
                await init_db()
                break
            except Exception as e:
                logger.error(f"Database init attempt {attempt + 1} failed: {e}")
                if attempt == 2:
                    raise
                await asyncio.sleep(2)
        
        # Initialize ML components (if available)
        if ML_AVAILABLE:
            trainer = ModelTrainer()
            await trainer.load_or_train_models()
            app.state.trainer = trainer
            
            # Initialize anomaly detector
            detector = AnomalyDetector()
            for model_type, model in trainer.active_models.items():
                detector.register_model(model_type, model)
            app.state.detector = detector
        else:
            logger.info("Running without ML components")
            app.state.trainer = None
            app.state.detector = None
        
        # Start background tasks
        app.state.feed_task = asyncio.create_task(feed.start_feed_ingestion())
        
        logger.info("Application startup complete")
        
    except Exception as e:
        logger.error("Failed to start application", error=str(e))
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

# CORS Middleware - Fixed configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Request ID middleware
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = f"req_{int(time.time() * 1000)}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# Exception handlers
@app.exception_handler(SubwayMonitorException)
async def subway_monitor_exception_handler(request, exc: SubwayMonitorException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )

# Mount routers
app.include_router(health.router, tags=["health"])
app.include_router(feed.router, prefix=f"{settings.api_v1_prefix}/feeds", tags=["feeds"])
app.include_router(anomaly.router, prefix=f"{settings.api_v1_prefix}/anomalies", tags=["anomalies"])
app.include_router(stations.router, prefix=f"{settings.api_v1_prefix}/stations", tags=["stations"])
app.include_router(websocket.router, prefix=f"{settings.api_v1_prefix}/ws", tags=["websocket"])

# Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "NYC Subway Monitor API",
        "version": settings.app_version,
        "docs": f"{settings.api_v1_prefix}/docs",
        "status": "operational"
    }

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # CRITICAL: Bind to all interfaces
        port=8000,
        reload=settings.debug,
        workers=1,  # Single worker for WebSocket support
        access_log=True,
        log_level="info",
    )