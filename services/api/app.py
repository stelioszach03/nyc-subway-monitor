# nyc-subway-monitor/services/api/app.py
import os
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import httpx
import redis
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Table, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import text
from prometheus_fastapi_instrumentator import Instrumentator

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

# Database setup with connection pooling
DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
engine = create_engine(
    DATABASE_URL,
    pool_size=20,           # Increase pool size
    max_overflow=0,        # No overflow
    pool_timeout=30.0,     # Wait max 30 seconds for connection  
    pool_recycle=3600,     # Recycle connections after 1 hour
    connect_args={
        "connect_timeout": 10  # 10 second connection timeout
    }
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Redis setup with timeout
redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    decode_responses=True,
    socket_timeout=5.0,     # 5 second timeout
    socket_connect_timeout=5.0,
    retry_on_timeout=True
)

# Create HTTP client with timeout for ML service calls
http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(3.0, connect=2.0),
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

def get_db():
    """Dependency for database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# API endpoints
@app.get("/trains", response_model=List[TrainPosition])
async def get_trains(
    route_id: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100)
):
    """Get current train positions, optionally filtered by route."""
    trains = []
    pattern = f"train:{route_id if route_id else '*'}:*"
    
    try:
        # Get train keys from Redis
        train_keys = redis_client.keys(pattern)
        
        for key in train_keys[:limit]:
            train_data = redis_client.hgetall(key)
            if not train_data:
                continue
                
            # Parse Redis key to get route_id and trip_id
            _, route, trip = key.split(":")
            
            # Skip if timestamp is older than 5 minutes
            timestamp = datetime.fromtimestamp(int(train_data.get("timestamp", 0)))
            if datetime.now() - timestamp > timedelta(minutes=5):
                continue
                
            trains.append({
                "route_id": route,
                "trip_id": trip,
                "timestamp": timestamp,
                "latitude": float(train_data.get("lat", 0)),
                "longitude": float(train_data.get("lon", 0)),
                "current_status": train_data.get("status", "UNKNOWN"),
                "delay": int(train_data.get("delay", 0)),
                "vehicle_id": train_data.get("vehicle_id", "unknown"),
                "direction_id": int(train_data.get("direction_id", 0))
            })
    except redis.TimeoutError:
        print("Redis timeout on /trains")
        return []
    except Exception as e:
        print(f"Error fetching trains: {e}")
        return []
    
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
        response = await http_client.get(f"{ML_SERVICE_URL}/anomalies", params=params)
        response.raise_for_status()
        return response.json()[:limit]
    except httpx.TimeoutException:
        print("ML service timeout on /anomalies")
        return []
    except httpx.HTTPError as e:
        print(f"Warning: ML service error: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []

@app.get("/subway-metrics", response_model=List[MetricResponse])
async def get_subway_metrics(
    db = Depends(get_db),
    route_id: Optional[str] = None,
    window: str = Query("5m", pattern=r"^\d+[mh]$")  # Format: 5m, 1h, etc.
):
    """Get aggregated metrics for the specified time window."""
    # Parse time window
    value = int(window[:-1])
    unit = window[-1]
    
    if unit == 'm':
        time_delta = timedelta(minutes=value)
    elif unit == 'h':
        time_delta = timedelta(hours=value)
    else:
        raise HTTPException(status_code=400, detail="Invalid window format")
    
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
        
    query += " GROUP BY route_id"
    
    # Execute query with timeout
    try:
        result = db.execute(text(query), params).fetchall()
    except Exception as e:
        print(f"Database query error: {e}")
        result = []
    
    # Get anomaly scores from ML service with timeout
    anomaly_scores = {}
    try:
        response = await http_client.get(f"{ML_SERVICE_URL}/scores")
        response.raise_for_status()
        scores = response.json()
        anomaly_scores = {item["route_id"]: item["score"] for item in scores}
    except (httpx.TimeoutException, httpx.HTTPError) as e:
        print(f"Warning: Could not fetch anomaly scores: {e}")
    except Exception as e:
        print(f"Unexpected error fetching scores: {e}")
    
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
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_update(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Subscribe to Redis pub/sub channel
    pubsub = redis_client.pubsub()
    pubsub.subscribe("train-updates")
    
    try:
        # Send initial state
        trains = await get_trains(limit=100)
        await websocket.send_json({"type": "initial", "data": trains})
        
        # Start listening for updates
        for message in pubsub.listen():
            if message["type"] == "message":
                # Forward Redis message to WebSocket client
                await websocket.send_text(message["data"].decode())
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        pubsub.unsubscribe()
    finally:
        pubsub.unsubscribe()

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

# Cleanup on shutdown
@app.on_event("shutdown")
async def shutdown_event():
    await http_client.aclose()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)