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

# Initialize Redis client
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

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

# Check if ONNX model exists
def load_model():
    """Load ONNX model for anomaly detection."""
    try:
        if not os.path.exists(MODEL_PATH):
            # Use a dummy model until the trained model is available
            return None
        
        # Load ONNX model
        session = ort.InferenceSession(MODEL_PATH)
        return session
    except Exception as e:
        print(f"Error loading model: {e}")
        return None

# Global model variable
onnx_model = load_model()

# Feature extraction
def extract_features(route_id: str) -> Dict[str, Any]:
    """Extract features for anomaly detection from Redis."""
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
    
    # Prepare features for ONNX model
    feature_names = ["mean_delay", "max_delay", "min_delay", "std_delay", "active_trains", "delay_per_train"]
    feature_vector = np.array([[features[name] for name in feature_names]], dtype=np.float32)
    
    # Run inference
    inputs = {onnx_model.get_inputs()[0].name: feature_vector}
    outputs = onnx_model.run(None, inputs)
    
    # Get anomaly score
    anomaly_score = outputs[0][0][0]  # Assuming the model outputs a single score
    
    return float(anomaly_score)

# API endpoints
@app.get("/scores", response_model=List[AnomalyScore])
async def get_anomaly_scores(
    route_id: Optional[str] = None
):
    """Get current anomaly scores for subway routes."""
    scores = []
    
    # Get all routes or the specified route
    if route_id:
        routes = [route_id]
    else:
        # Extract unique route IDs from Redis keys
        route_keys = redis_client.keys("train:*:*")
        routes = set()
        for key in route_keys:
            parts = key.split(":")
            if len(parts) >= 2:
                routes.add(parts[1])
    
    # Calculate anomaly score for each route
    for route in routes:
        features = extract_features(route)
        if features:
            score = score_anomaly(features)
            
            # Store score in Redis
            redis_client.hset(
                f"anomaly:{route}", 
                mapping={
                    "score": score,
                    "timestamp": int(datetime.now().timestamp())
                }
            )
            
            scores.append({
                "route_id": route,
                "score": score,
                "timestamp": datetime.now()
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