# nyc-subway-monitor/services/ml/score.py
import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import onnxruntime as ort
import redis
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator

# Environment variables
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
MODEL_PATH = os.environ.get("MODEL_PATH", "/app/models/anomaly_model.onnx")

# Initialize FastAPI
app = FastAPI(
    title="NYC Subway ML Service",
    description="Anomaly detection for NYC Subway data",
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

# Initialize Redis client with timeout
redis_client = redis.Redis(
    host=REDIS_HOST, 
    port=REDIS_PORT, 
    decode_responses=True,
    socket_timeout=5.0,
    socket_connect_timeout=5.0,
    retry_on_timeout=True
)

# Pydantic models
class AnomalyScore(BaseModel):
    route_id: str
    score: float
    timestamp: datetime

class Alert(BaseModel):
    id: str
    route_id: str
    timestamp: datetime
    message: str
    severity: str
    anomaly_score: float

# Global model variable - will be loaded on startup
onnx_model = None

# Load model on startup for fast responses
@app.on_event("startup")
async def startup_event():
    """Load ONNX model during startup for faster responses."""
    global onnx_model
    
    print(f"Starting ML service...")
    print(f"Looking for model at: {MODEL_PATH}")
    
    try:
        if os.path.exists(MODEL_PATH):
            # Load ONNX model
            print("Model file found, loading...")
            onnx_model = ort.InferenceSession(MODEL_PATH)
            print(f"Model loaded successfully from {MODEL_PATH}")
        else:
            print(f"Model not found at {MODEL_PATH}, using fallback scoring")
            onnx_model = None
    except Exception as e:
        print(f"Error loading model: {e}, using fallback scoring")
        onnx_model = None
    
    print("ML service startup complete")

# Simple cache to speed up responses
_route_cache = {}
_cache_timestamp = {}
CACHE_TTL = 30  # seconds

# Feature extraction
def extract_features(route_id: str) -> Optional[Dict[str, Any]]:
    """Extract features for anomaly detection from Redis."""
    try:
        # Get current train positions for the route
        pattern = f"train:{route_id}:*"
        train_keys = redis_client.keys(pattern)
        
        if not train_keys:
            return None
        
        # Collect delay and position data
        delays = []
        active_trains = 0
        
        for key in train_keys:
            train_data = redis_client.hgetall(key)
            if not train_data:
                continue
                
            # Parse Redis data
            timestamp = int(train_data.get("timestamp", 0))
            if datetime.now().timestamp() - timestamp > 300:  # Skip data older than 5 minutes
                continue
                
            delay = int(train_data.get("delay", 0))
            delays.append(delay)
            active_trains += 1
        
        if not delays:
            return None
        
        # Calculate feature vector
        features = {
            "route_id": route_id,
            "mean_delay": np.mean(delays),
            "max_delay": np.max(delays),
            "min_delay": np.min(delays),
            "std_delay": np.std(delays),
            "active_trains": active_trains,
            "delay_per_train": np.mean(delays) / max(1, active_trains)
        }
        
        return features
    except redis.TimeoutError:
        print(f"Redis timeout for route {route_id}")
        return None
    except Exception as e:
        print(f"Error extracting features for route {route_id}: {e}")
        return None

def score_anomaly(features: Dict[str, Any]) -> float:
    """Score anomaly using ONNX model or fallback method."""
    if onnx_model is None:
        # Fallback: simple heuristic
        if features["mean_delay"] > 300:  # More than 5 minutes average delay
            return 0.9
        elif features["max_delay"] > 600:  # Any train more than 10 minutes delayed
            return 0.8
        elif features["std_delay"] > 200:  # High variance in delays
            return 0.7
        else:
            return 0.1
    
    try:
        # Prepare features for ONNX model
        feature_names = ["mean_delay", "max_delay", "min_delay", "std_delay", "active_trains", "delay_per_train"]
        feature_vector = np.array([[features[name] for name in feature_names]], dtype=np.float32)
        
        # Run inference
        inputs = {onnx_model.get_inputs()[0].name: feature_vector}
        outputs = onnx_model.run(None, inputs)
        
        # Get anomaly score
        anomaly_score = outputs[0][0][0]  # Assuming the model outputs a single score
        
        return float(anomaly_score)
    except Exception as e:
        print(f"Error running inference: {e}")
        # Fallback to heuristic
        return score_anomaly(features) if onnx_model is None else 0.5

# API endpoints
@app.get("/scores", response_model=List[AnomalyScore])
async def get_anomaly_scores(
    route_id: Optional[str] = None
):
    """Get current anomaly scores for subway routes."""
    current_time = datetime.now()
    scores = []
    
    # Get all routes or the specified route
    if route_id:
        routes = [route_id]
    else:
        try:
            # Extract unique route IDs from Redis keys
            route_keys = redis_client.keys("train:*:*")
            routes = set()
            for key in route_keys:
                parts = key.split(":")
                if len(parts) >= 2:
                    routes.add(parts[1])
        except redis.TimeoutError:
            print("Redis timeout getting routes")
            return []
        except Exception as e:
            print(f"Error getting routes: {e}")
            return []
    
    # Calculate anomaly score for each route
    for route in routes:
        # Check cache first
        cache_key = f"score_{route}"
        if cache_key in _route_cache and cache_key in _cache_timestamp:
            if (current_time - _cache_timestamp[cache_key]).total_seconds() < CACHE_TTL:
                score = _route_cache[cache_key]
                scores.append({
                    "route_id": route,
                    "score": score,
                    "timestamp": current_time
                })
                continue
        
        # Calculate fresh score
        features = extract_features(route)
        if features:
            score = score_anomaly(features)
            
            # Update cache
            _route_cache[cache_key] = score
            _cache_timestamp[cache_key] = current_time
            
            # Store score in Redis
            try:
                redis_client.hset(
                    f"anomaly:{route}", 
                    mapping={
                        "score": score,
                        "timestamp": int(current_time.timestamp())
                    }
                )
            except redis.TimeoutError:
                print(f"Redis timeout storing score for {route}")
            
            scores.append({
                "route_id": route,
                "score": score,
                "timestamp": current_time
            })
    
    return scores

@app.get("/anomalies", response_model=List[Alert])
async def get_anomalies(
    route_id: Optional[str] = None,
    severity: Optional[str] = None,
    threshold: float = Query(0.7, ge=0, le=1)
):
    """Get current anomalies above the threshold."""
    # Get fresh anomaly scores
    scores = await get_anomaly_scores(route_id)
    
    # Filter anomalies by threshold
    anomalies = []
    for item in scores:
        if item["score"] >= threshold:
            # Determine severity based on score
            if item["score"] >= 0.9:
                severity_level = "HIGH"
            elif item["score"] >= 0.7:
                severity_level = "MEDIUM"
            else:
                severity_level = "LOW"
                
            # Skip if severity filter doesn't match
            if severity and severity != severity_level:
                continue
                
            # Generate alert message
            message = f"Abnormal delays detected on {item['route_id']} line"
            
            # Create alert
            alert_id = f"{item['route_id']}_{int(datetime.now().timestamp())}"
            anomalies.append({
                "id": alert_id,
                "route_id": item["route_id"],
                "timestamp": item["timestamp"],
                "message": message,
                "severity": severity_level,
                "anomaly_score": item["score"]
            })
    
    return anomalies

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    model_status = "loaded" if onnx_model is not None else "not_loaded"
    return {
        "status": "ok",
        "model_status": model_status,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)