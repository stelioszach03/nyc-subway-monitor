# services/api/app.py - key improvements
import os
import sys
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import httpx
import asyncio
import json
# Προσθήκη του DateTimeEncoder για τη σειριοποίηση των datetime
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

# Use the correct import for different Python versions
if sys.version_info >= (3, 11, 3):
    from asyncio import timeout as async_timeout
else:
    from async_timeout import timeout as async_timeout

import redis.asyncio as redis  # Using async redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from prometheus_fastapi_instrumentator import Instrumentator

# Set up logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("api_service")

# Environment configuration
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "timescaledb")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "subway")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "subway_password")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "subway_monitor")
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml:8000")

# Initialize FastAPI app
app = FastAPI(
    title="NYC Subway Monitor API",
    description="Real-time monitoring of the NYC Subway system",
    version="1.0.0"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )

# Database setup with connection pooling and retry logic
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Create engine with improved parameters for reliability
def get_db_engine():
    """Create database engine with retry mechanism."""
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            logger.info(f"Creating database engine (attempt {attempt+1}/{max_attempts})...")
            engine = create_engine(
                DATABASE_URL,
                pool_size=20,           
                max_overflow=0,        
                pool_timeout=30.0,     
                pool_recycle=3600,     
                connect_args={
                    "connect_timeout": 10  
                }
            )
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return engine
        except Exception as e:
            if attempt < max_attempts - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Database connection failed: {e}. Retrying in {wait_time}s...")
                asyncio.sleep(wait_time)
            else:
                logger.error(f"Database connection failed after {max_attempts} attempts: {e}")
                raise

# Initialize engine
engine = None
try:
    engine = get_db_engine()
except Exception as e:
    logger.error(f"Failed to initialize database engine: {e}")
    logger.warning("API will start but database functionality will be limited until connection is established")

# Create session factory if engine is available
SessionLocal = None
if engine:
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis setup - ASYNC VERSION
redis_client = None
pubsub_connections = {}

@app.on_event("startup")
async def startup_event():
    global redis_client, engine, SessionLocal
    
    # Create async Redis client with retry
    max_attempts = 5
    for attempt in range(max_attempts):
        try:
            logger.info(f"Connecting to Redis (attempt {attempt+1}/{max_attempts})...")
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                encoding="utf-8",
                max_connections=20,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True
            )
            # Test connection
            await redis_client.ping()
            logger.info(f"Connected to Redis at {REDIS_HOST}:{REDIS_PORT}")
            break
        except Exception as e:
            if attempt < max_attempts - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Redis connection failed: {e}. Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Redis connection failed after {max_attempts} attempts: {e}")
                redis_client = None
    
    # Retry database connection if it failed initially
    if engine is None:
        try:
            engine = get_db_engine()
            if engine:
                SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
                logger.info("Database connection established during startup")
        except Exception as e:
            logger.error(f"Failed to initialize database engine during startup: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    global redis_client, http_client
    
    # Close Redis client
    if redis_client:
        try:
            await redis_client.close()
            logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}")
    
    # Close all pubsub connections
    for pubsub in pubsub_connections.values():
        try:
            await pubsub.close()
        except Exception as e:
            logger.error(f"Error closing pubsub connection: {e}")
    
    # Close HTTP client
    try:
        await http_client.aclose()
        logger.info("HTTP client closed")
    except Exception as e:
        logger.error(f"Error closing HTTP client: {e}")

# Create HTTP client with timeout and retry for ML service calls
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(10.0, connect=3.0),
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
)

# Configure transport with retry
transport = httpx.AsyncHTTPTransport(retries=3)
http_client = httpx.AsyncClient(
    transport=transport,
    timeout=httpx.Timeout(10.0, connect=3.0),
    limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
)

# Pydantic models
class TrainPosition(BaseModel):
    trip_id: str
    route_id: str
    timestamp: datetime
    latitude: float
    longitude: float
    current_status: str
    current_stop_sequence: Optional[int] = None
    delay: Optional[int] = None
    vehicle_id: str
    direction_id: int

class RouteDelay(BaseModel):
    route_id: str
    avg_delay: float
    max_delay: int
    min_delay: int
    train_count: int
    window_start: datetime
    window_end: datetime

class Alert(BaseModel):
    id: str
    route_id: str
    timestamp: datetime
    message: str
    severity: str
    anomaly_score: float

class MetricResponse(BaseModel):
    route_id: str
    avg_delay: float
    train_count: int
    anomaly_score: Optional[float] = None
    timestamp: datetime

# Database session dependency with better error handling
def get_db():
    """Dependency for database session."""
    if SessionLocal is None:
        raise HTTPException(
            status_code=503, 
            detail="Database connection is not available"
        )
        
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        raise HTTPException(
            status_code=500,
            detail="Database error occurred"
        )
    finally:
        db.close()

# API endpoints with improved error handling and performance
@app.get("/trains", response_model=List[TrainPosition])
async def get_trains(
    route_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100)
):
    """Get current train positions, optionally filtered by route."""
    if redis_client is None:
        raise HTTPException(
            status_code=503,
            detail="Redis connection is not available"
        )
        
    trains = []
    pattern = f"train:{route_id if route_id else '*'}:*"
    
    try:
        # Get train keys from Redis
        train_keys = await redis_client.keys(pattern)
        
        # Use Redis pipeline for efficient batch retrieval
        pipe = redis_client.pipeline()
        for key in train_keys[:limit]:
            pipe.hgetall(key)
        
        # Execute pipeline
        results = await pipe.execute()
        
        # Process results
        for i, key in enumerate(train_keys[:limit]):
            try:
                train_data = results[i]
                if not train_data:
                    continue
                    
                # Parse Redis key to get route_id and trip_id
                parts = key.split(":")
                if len(parts) >= 3:
                    route, trip = parts[1], parts[2]
                else:
                    continue
                
                # Skip if timestamp is older than 5 minutes
                # Skip if timestamp is older than 15 minutes (αύξηση από 5 σε 15 λεπτά)
                try:
                    timestamp = datetime.fromtimestamp(int(train_data.get("timestamp", 0)))
                    if datetime.now() - timestamp > timedelta(minutes=15):
                        continue
                except (ValueError, TypeError):
                    # Fallback to current timestamp if parsing fails
                    timestamp = datetime.now()
                    
                try:
                    train = {
                        "route_id": route,
                        "trip_id": trip,
                        "timestamp": timestamp,  # Τώρα είναι datetime αντικείμενο
                        "latitude": float(train_data.get("lat", 0)),
                        "longitude": float(train_data.get("lon", 0)),
                        "current_status": train_data.get("status", "UNKNOWN"),
                        "delay": int(train_data.get("delay", 0)),
                        "vehicle_id": train_data.get("vehicle_id", "unknown"),
                        "direction_id": int(train_data.get("direction_id", 0))
                    }
                    trains.append(train)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error parsing train data for {key}: {e}")
                    continue
            except Exception as e:
                logger.warning(f"Error processing train data for key {key}: {e}")
                continue
    except redis.RedisError as e:
        logger.error(f"Redis error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Error retrieving train data from Redis"
        )
    except Exception as e:
        logger.error(f"Error fetching trains: {e}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred"
        )
    
    return trains

@app.get("/alerts", response_model=List[Alert])
async def get_alerts(
    route_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = Query(20, ge=1, le=50)
):
    """Get recent alerts, optionally filtered by route and severity."""
    # Query ML service for anomalies with timeout
    params = {}
    if route_id:
        params["route_id"] = route_id
    if severity:
        params["severity"] = severity
        
    try:
        # Use async timeout to prevent hanging
        async with async_timeout(10):
            response = await http_client.get(f"{ML_SERVICE_URL}/anomalies", params=params)
            response.raise_for_status()
            return response.json()[:limit]
    except asyncio.TimeoutError:
        logger.warning("ML service request timed out")
        return []
    except httpx.HTTPStatusError as e:
        logger.warning(f"ML service error: {e.response.status_code} - {e.response.text}")
        return []
    except httpx.RequestError as e:
        logger.warning(f"ML service request error: {e}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error getting alerts: {e}")
        return []

@app.get("/subway-metrics", response_model=List[MetricResponse])
async def get_subway_metrics(
    route_id: Optional[str] = None,
    window: str = Query("5m", pattern=r"^\d+[mh]$")  
):
    """Get aggregated metrics for the specified time window."""
    # Parse time window
    try:
        value = int(window[:-1])
        unit = window[-1]
        
        if unit == 'm':
            time_delta = timedelta(minutes=value)
        elif unit == 'h':
            time_delta = timedelta(hours=value)
        else:
            raise HTTPException(status_code=400, detail="Invalid window format")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid window value")
    
    start_time = datetime.now() - time_delta
    
    # Query for aggregated metrics
    query = """
    SELECT 
        route_id, 
        AVG(avg_delay) as avg_delay, 
        SUM(train_count) as train_count, 
        MAX(window_end) as timestamp 
    FROM train_delays 
    WHERE window_end > :start_time
    """
    
    params = {"start_time": start_time}
    
    if route_id:
        query += " AND route_id = :route_id"
        params["route_id"] = route_id
        
    query += " GROUP BY route_id ORDER BY AVG(avg_delay) DESC"
    
    # Execute query with timeout and connection check
    try:
        if SessionLocal is None:
            logger.warning("Database connection not available for metrics query")
            result = []
        else:
            db = SessionLocal()
            try:
                # Set statement timeout to prevent long-running queries
                db.execute(text("SET statement_timeout = '10s'"))
                result = db.execute(text(query), params).fetchall()
            finally:
                db.close()
    except Exception as e:
        logger.error(f"Database query error: {e}")
        result = []
    
    # Get anomaly scores from ML service with timeout
    anomaly_scores = {}
    try:
        async with async_timeout(5):  # 5 second timeout
            response = await http_client.get(f"{ML_SERVICE_URL}/scores")
            if response.status_code == 200:
                scores = response.json()
                anomaly_scores = {item["route_id"]: item["score"] for item in scores}
    except asyncio.TimeoutError:
        logger.warning("ML service timeout for anomaly scores")
    except httpx.HTTPError as e:
        logger.warning(f"ML service error for anomaly scores: {e}")
    except Exception as e:
        logger.error(f"Unexpected error fetching anomaly scores: {e}")
    
    # Combine database results with anomaly scores
    metrics = []
    for row in result:
        route = row[0]
        metrics.append({
            "route_id": route,
            "avg_delay": float(row[1]),
            "train_count": int(row[2]),
            "anomaly_score": anomaly_scores.get(route),
            "timestamp": row[3]
        })
    
    return metrics

# WebSocket connection for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        async with self.lock:
            self.active_connections[client_id] = websocket
            logger.info(f"Client {client_id} connected. Active connections: {len(self.active_connections)}")

    async def disconnect(self, client_id: str):
        async with self.lock:
            if client_id in self.active_connections:
                del self.active_connections[client_id]
                logger.info(f"Client {client_id} disconnected. Active connections: {len(self.active_connections)}")

    async def send_update(self, message: str):
        if not self.active_connections:
            return
            
        disconnected_clients = []
        
        # Use copy to avoid RuntimeError when dictionary changes during iteration
        async with self.lock:
            clients = list(self.active_connections.items())
        
        for client_id, connection in clients:
            try:
                await connection.send_text(message)
            except WebSocketDisconnect:
                disconnected_clients.append(client_id)
            except Exception as e:
                logger.warning(f"Error sending update to client {client_id}: {e}")
                disconnected_clients.append(client_id)
        
        # Remove disconnected connections
        if disconnected_clients:
            async with self.lock:
                for client_id in disconnected_clients:
                    if client_id in self.active_connections:
                        del self.active_connections[client_id]
            logger.info(f"Removed {len(disconnected_clients)} disconnected clients. Active connections: {len(self.active_connections)}")

manager = ConnectionManager()

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    # Generate a unique client ID
    client_id = f"client_{int(datetime.now().timestamp())}_{id(websocket)}"
    
    await manager.connect(websocket, client_id)
    
    # Create a dedicated pubsub connection for this WebSocket
    pubsub = None
    
    try:
        if redis_client is None:
            raise Exception("Redis connection is not available")
            
        pubsub = redis_client.pubsub()
        
        # Send initial state
        try:
            trains = await get_trains(limit=100)
            # Χρησιμοποιούμε τον DateTimeEncoder για σειριοποίηση των datetime αντικειμένων
            await websocket.send_text(json.dumps({"type": "initial", "data": trains}, cls=DateTimeEncoder))
        except Exception as e:
            logger.warning(f"Error sending initial train data: {e}")
            # Continue even if initial data fails
        
        # Subscribe to updates
        await pubsub.subscribe("train-updates")
        
        # Store pubsub connection for cleanup
        pubsub_connections[client_id] = pubsub
        
        # Start listening for updates - ASYNC VERSION with proper timeout
        while True:
            try:
                # Use timeout to allow graceful disconnection
                async with async_timeout(10):
                    message = await pubsub.get_message(ignore_subscribe_messages=True)
                    
                    if message and message["type"] == "message":
                        # Forward Redis message to WebSocket client
                        try:
                            await websocket.send_text(message["data"])
                        except WebSocketDisconnect:
                            logger.info(f"Client {client_id} disconnected during message send")
                            break
                        except Exception as e:
                            logger.warning(f"Error sending message to client {client_id}: {e}")
                            break
                        
            except asyncio.TimeoutError:
                # Send a keepalive ping
                try:
                    # Χρησιμοποιούμε τον DateTimeEncoder για το ping
                    await websocket.send_text(json.dumps({"type": "ping"}, cls=DateTimeEncoder))
                except WebSocketDisconnect:
                    logger.info(f"Client {client_id} disconnected during ping")
                    break
                except Exception as e:
                    logger.warning(f"Error sending ping to client {client_id}: {e}")
                    break
                    
            except Exception as e:
                logger.error(f"Error in websocket message loop for client {client_id}: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")
    finally:
        await manager.disconnect(client_id)
        
        if pubsub:
            try:
                await pubsub.unsubscribe("train-updates")
                await pubsub.close()
                
                # Remove from connections dictionary
                if client_id in pubsub_connections:
                    del pubsub_connections[client_id]
            except Exception as e:
                logger.warning(f"Error closing pubsub for client {client_id}: {e}")
        
# Health check endpoint
@app.get("/health")
async def health_check():
    health_data = {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "components": {}
    }
    
    # Check Redis connection
    try:
        if redis_client:
            redis_status = await redis_client.ping()
            health_data["components"]["redis"] = {"status": "connected" if redis_status else "error"}
        else:
            health_data["components"]["redis"] = {"status": "not_connected"}
    except Exception as e:
        health_data["components"]["redis"] = {"status": f"error: {str(e)}"}
    
    # Check database connection
    try:
        if SessionLocal:
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1")).fetchone()
                health_data["components"]["database"] = {"status": "connected"}
            except Exception as e:
                health_data["components"]["database"] = {"status": f"error: {str(e)}"}
            finally:
                db.close()
        else:
            health_data["components"]["database"] = {"status": "not_connected"}
    except Exception as e:
        health_data["components"]["database"] = {"status": f"error: {str(e)}"}
    
    # Check ML service
    try:
        async with async_timeout(2):  # 2 second timeout
            response = await http_client.get(f"{ML_SERVICE_URL}/health")
            if response.status_code == 200:
                ml_data = response.json()
                health_data["components"]["ml_service"] = {
                    "status": "connected",
                    "model_status": ml_data.get("model_status", "unknown"),
                    "model_type": ml_data.get("model_type", "unknown")
                }
            else:
                health_data["components"]["ml_service"] = {"status": f"error: {response.status_code}"}
    except Exception as e:
        health_data["components"]["ml_service"] = {"status": f"error: {str(e)}"}
    
    # Check active WebSocket connections
    health_data["components"]["websocket"] = {
        "active_connections": len(manager.active_connections)
    }
    
    # Overall status based on component health
    component_statuses = [
        comp["status"] for comp in health_data["components"].values() 
        if isinstance(comp, dict) and "status" in comp
    ]
    
    if any(status.startswith("error") for status in component_statuses):
        health_data["status"] = "degraded"
    
    if all(status == "not_connected" or status.startswith("error") for status in component_statuses):
        health_data["status"] = "critical"
    
    return health_data

if __name__ == "__main__":
    import uvicorn
    workers = int(os.environ.get("WORKERS", "4"))
    uvicorn.run(
        "app:app", 
        host="0.0.0.0", 
        port=8000, 
        workers=workers,
        log_level=os.environ.get("LOG_LEVEL", "info").lower()
    )