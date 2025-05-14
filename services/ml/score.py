# services/ml/score.py - key improvements
import os
import json
import time
import threading
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging

import numpy as np
import pandas as pd
import onnxruntime as ort
import redis
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
import pickle
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ml_service")

# Environment variables
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
MODEL_PATH = os.environ.get("MODEL_PATH", "/app/models/anomaly_model.onnx")
AUTO_CREATE_MODEL = os.environ.get("AUTO_CREATE_MODEL", "true").lower() == "true"
MODEL_RELOAD_INTERVAL = int(os.environ.get("MODEL_RELOAD_INTERVAL", "60"))  # 60 seconds

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

# Global model variables
model_lock = threading.RLock()  # Reentrant lock for thread safety
onnx_model = None
scaler = None
feature_columns = None
model_last_modified = None
model_last_checked = 0

# Thread pool for background tasks
executor = ThreadPoolExecutor(max_workers=2)

# Define SimpleAnomalyModel at module level
class SimpleAnomalyModel:
    """A simple model that calculates anomaly scores based on delay values."""
    def predict(self, X):
        """
        Calculate anomaly score based on input features.
        Higher avg_delay and max_delay lead to higher scores.
        More trains with low delay score lower (more normal).
        """
        scores = []
        for x in X:
            # Basic formula: avg_delay impacts most, train_count is inversely related
            avg_delay = x[0] if len(x) > 0 else 0  # First feature assumed to be avg_delay
            max_delay = x[1] if len(x) > 1 else 0  # Second feature assumed to be max_delay
            train_count = x[4] if len(x) > 4 else 1  # Fifth feature assumed to be train_count
            
            # Base score calculation
            base_score = min(0.95, (avg_delay / 600) * 0.8)  # 10min max_delay → 0.8 score
            
            # Increase score for high max_delay
            if max_delay > 600:  # 10 minutes
                base_score = min(0.95, base_score + 0.2)
                
            # Reduce score if many trains (likely systemic, not anomalous)
            if train_count > 3:
                base_score = max(0.1, base_score - (min(train_count, 10) / 20))
                
            scores.append(base_score)
            
        return np.array(scores)

# Function to create a fallback model
def create_fallback_model():
    """Creates a simple model if none exists."""
    logger.info("Creating fallback model...")
    
    # Ensure the models directory exists
    os.makedirs('/app/models', exist_ok=True)
    
    # Create a simple model
    model = SimpleAnomalyModel()
    
    # Save the model
    model_path = "/app/models/anomaly_model.pkl"
    with open(model_path, 'wb') as f:
        pickle.dump(model, f)
    
    # Create feature_info.json
    feature_info = {
        "feature_columns": [
            "avg_delay", "max_delay", "min_delay", "delay_std", 
            "train_count", "delay_per_train"
        ],
        "trained_at": datetime.now().isoformat()
    }
    
    with open('/app/models/feature_info.json', 'w') as f:
        json.dump(feature_info, f, indent=2)
    
    logger.info(f"Fallback model created at {model_path}")
    return model

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

# Custom exception handler
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )

# Monitor for model updates
def check_model_updates():
    global onnx_model, scaler, feature_columns, model_last_modified, model_last_checked
    
    now = time.time()
    # Only check periodically
    if now - model_last_checked < MODEL_RELOAD_INTERVAL:
        return
    
    with model_lock:
        model_last_checked = now
        
        try:
            # Check if model file exists and has been modified
            onnx_path = MODEL_PATH
            pkl_path = MODEL_PATH.replace('.onnx', '.pkl')
            
            # Check both possible paths
            if os.path.exists(onnx_path):
                current_mtime = os.path.getmtime(onnx_path)
                if model_last_modified is None or current_mtime > model_last_modified:
                    logger.info(f"Detected new/updated model at {onnx_path}, reloading...")
                    model_last_modified = current_mtime
                    reload_model()
            elif os.path.exists(pkl_path):
                current_mtime = os.path.getmtime(pkl_path)
                if model_last_modified is None or current_mtime > model_last_modified:
                    logger.info(f"Detected new/updated model at {pkl_path}, reloading...")
                    model_last_modified = current_mtime
                    reload_model()
        except Exception as e:
            logger.error(f"Error checking for model updates: {e}", exc_info=True)

def reload_model():
    """Reload model from disk with thread safety."""
    global onnx_model, scaler, feature_columns, model_last_modified
    
    with model_lock:
        try:
            # Check for different model file types
            onnx_path = MODEL_PATH
            pkl_path = MODEL_PATH.replace('.onnx', '.pkl')
            
            new_model = None
            
            if os.path.exists(onnx_path):
                logger.info("Loading ONNX model...")
                # Use try-finally to ensure we don't leave the model in an inconsistent state
                try:
                    new_model = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
                    model_last_modified = os.path.getmtime(onnx_path)
                    logger.info("ONNX model loaded successfully")
                except Exception as e:
                    logger.error(f"Error loading ONNX model: {e}", exc_info=True)
                    return
            elif os.path.exists(pkl_path):
                logger.info("Loading pickle model...")
                try:
                    with open(pkl_path, 'rb') as f:
                        new_model = pickle.load(f)
                    model_last_modified = os.path.getmtime(pkl_path)
                    logger.info("Pickle model loaded successfully")
                except Exception as e:
                    logger.error(f"Error loading pickle model: {e}", exc_info=True)
                    return
            else:
                logger.warning("No model found to reload")
                return
            
            # If we got here, model loaded successfully, now load scaler and feature info
            
            # Reload scaler
            new_scaler = None
            scaler_path = "/app/models/scaler.pkl"
            if os.path.exists(scaler_path):
                try:
                    with open(scaler_path, 'rb') as f:
                        new_scaler = pickle.load(f)
                except Exception as e:
                    logger.error(f"Error loading scaler: {e}", exc_info=True)
            
            # Reload feature info
            new_feature_columns = None
            feature_info_path = "/app/models/feature_info.json"
            if os.path.exists(feature_info_path):
                try:
                    with open(feature_info_path, 'r') as f:
                        feature_info = json.load(f)
                        new_feature_columns = feature_info.get('feature_columns')
                except Exception as e:
                    logger.error(f"Error loading feature info: {e}", exc_info=True)
            
            # Now that everything has loaded successfully, update the global variables atomically
            onnx_model = new_model
            scaler = new_scaler
            feature_columns = new_feature_columns
            
            # Clear cache to force new scores
            _route_cache.clear()
            _cache_timestamp.clear()
            
            logger.info("Model, scaler, and feature columns reloaded successfully")
        except Exception as e:
            logger.error(f"Error reloading model: {e}", exc_info=True)

# Load model on startup for fast responses
@app.on_event("startup")
async def startup_event():
    """Load model during startup for faster responses."""
    global onnx_model, scaler, feature_columns, model_last_modified
    
    logger.info(f"Starting ML service...")
    logger.info(f"Looking for model at: {MODEL_PATH}")
    
    try:
        # Check for different model file types
        onnx_path = MODEL_PATH
        pkl_path = MODEL_PATH.replace('.onnx', '.pkl')
        scaler_path = "/app/models/scaler.pkl"
        feature_info_path = "/app/models/feature_info.json"
        
        if os.path.exists(onnx_path):
            logger.info("Loading ONNX model...")
            onnx_model = ort.InferenceSession(onnx_path, providers=['CPUExecutionProvider'])
            model_last_modified = os.path.getmtime(onnx_path)
            logger.info(f"ONNX model loaded successfully from {onnx_path}")
        elif os.path.exists(pkl_path):
            logger.info("Loading pickle model...")
            with open(pkl_path, 'rb') as f:
                onnx_model = pickle.load(f)
            model_last_modified = os.path.getmtime(pkl_path)
            logger.info(f"Pickle model loaded successfully from {pkl_path}")
        elif AUTO_CREATE_MODEL:
            logger.info("No model found. Creating fallback model automatically...")
            onnx_model = create_fallback_model()
            model_last_modified = time.time()
            logger.info("Fallback model created and loaded")
        else:
            logger.warning(f"No model found at {onnx_path} or {pkl_path}, using fallback scoring")
            onnx_model = None
        
        # Load scaler and feature info if they exist
        if os.path.exists(scaler_path) and scaler is None:
            logger.info("Loading scaler...")
            with open(scaler_path, 'rb') as f:
                scaler = pickle.load(f)
            logger.info("Scaler loaded successfully")
        
        if os.path.exists(feature_info_path):
            logger.info("Loading feature info...")
            with open(feature_info_path, 'r') as f:
                feature_info = json.load(f)
                feature_columns = feature_info.get('feature_columns')
            logger.info(f"Feature columns loaded: {feature_columns}")
        elif AUTO_CREATE_MODEL and feature_columns is None:
            feature_columns = [
                "avg_delay", "max_delay", "min_delay", "delay_std", 
                "train_count", "delay_per_train"
            ]
            logger.info(f"Using default feature columns: {feature_columns}")
        
        # Start model update checking in a background thread
        logger.info(f"Starting model update checking every {MODEL_RELOAD_INTERVAL} seconds")
        
        # Schedule periodic model checking
        def scheduled_check():
            while True:
                try:
                    check_model_updates()
                except Exception as e:
                    logger.error(f"Error in scheduled model check: {e}", exc_info=True)
                time.sleep(MODEL_RELOAD_INTERVAL)
        
        # Start the background thread
        threading.Thread(target=scheduled_check, daemon=True).start()
        
    except Exception as e:
        logger.error(f"Error loading model: {e}", exc_info=True)
        onnx_model = None
        scaler = None
        feature_columns = None
    
    logger.info("ML service startup complete")
    model_type = 'ONNX' if isinstance(onnx_model, ort.InferenceSession) else 'Custom Model' if onnx_model else 'Fallback'
    logger.info(f"Model type: {model_type}")

# On shutdown cleanup
@app.on_event("shutdown")
async def shutdown_event():
    # Clean up resources
    executor.shutdown(wait=False)
    logger.info("ML service shutting down")

# Simple cache to speed up responses
_route_cache = {}
_cache_timestamp = {}
CACHE_TTL = 30  # seconds

# Feature extraction
def extract_features(route_id: str) -> Optional[Dict[str, Any]]:
    """Extract features for anomaly detection from Redis."""
    try:
        # Check for model updates
        check_model_updates()
        
        # Get current train positions for the route
        pattern = f"train:{route_id}:*"
        train_keys = redis_client.keys(pattern)
        
        if not train_keys:
            return None
        
        # Collect delay and position data
        delays = []
        active_trains = 0
        
        for key in train_keys:
            try:
                train_data = redis_client.hgetall(key)
                if not train_data:
                    continue
                    
                # Parse Redis data
                timestamp_str = train_data.get("timestamp", "0")
                try:
                    timestamp = int(timestamp_str)
                except (ValueError, TypeError):
                    timestamp = 0
                
                if datetime.now().timestamp() - timestamp > 300:  # Skip data older than 5 minutes
                    continue
                
                try:
                    delay = int(train_data.get("delay", 0))
                except (ValueError, TypeError):
                    delay = 0
                
                delays.append(delay)
                active_trains += 1
            except redis.RedisError as e:
                logger.warning(f"Redis error on key {key}: {e}")
                continue
        
        if not delays:
            return None
        
        # Calculate feature vector based on current time
        current_time = datetime.now()
        hour = current_time.hour
        day_of_week = current_time.weekday()
        is_weekend = 1 if day_of_week in [5, 6] else 0
        
        # Calculate delay statistics
        delay_array = np.array(delays)
        delay_mean = np.mean(delays)
        delay_max = np.max(delays)
        delay_min = np.min(delays)
        delay_std = np.std(delays) if len(delays) > 1 else 0
        
        # Calculate feature vector - should match training features
        features = {
            "avg_delay": delay_mean,
            "max_delay": delay_max,
            "min_delay": delay_min,
            "delay_std": delay_std,
            "train_count": active_trains,
            "delay_per_train": delay_mean / max(1, active_trains),
            "delay_variability": delay_std / max(1, active_trains),
            "hour": hour,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
            "active_vehicles": active_trains  # Use train count as proxy for vehicles
        }
        
        return features
    except redis.TimeoutError:
        logger.warning(f"Redis timeout for route {route_id}")
        return None
    except Exception as e:
        logger.error(f"Error extracting features for route {route_id}: {e}", exc_info=True)
        return None

def score_anomaly(features: Dict[str, Any]) -> float:
    """Score anomaly using ONNX model or fallback method."""
    global onnx_model, scaler, feature_columns
    
    with model_lock:
        # Check for model updates
        check_model_updates()
        
        # Fallback heuristic if no model is loaded
        if onnx_model is None:
            # Simple heuristic based on delay values
            if features["avg_delay"] > 300:  # More than 5 minutes average delay
                return 0.9
            elif features["max_delay"] > 600:  # Any train more than 10 minutes delayed
                return 0.8
            elif features["delay_std"] > 200:  # High variance in delays
                return 0.7
            else:
                return max(0.1, min(0.6, features["avg_delay"] / 600))  # Scale delay to [0.1, 0.6]
        
        try:
            # Use model-trained feature columns or fall back to default
            if feature_columns is None:
                feature_names = [
                    'avg_delay', 'max_delay', 'min_delay', 'delay_std',
                    'train_count', 'delay_per_train', 'delay_variability',
                    'hour', 'day_of_week', 'is_weekend', 'active_vehicles'
                ]
            else:
                feature_names = feature_columns
            
            # Create feature vector - only include features that exist in model
            feature_vector = np.array([[features.get(name, 0.0) for name in feature_names if name in features]], dtype=np.float32)
            
            # Apply scaling if scaler is available
            if scaler is not None:
                try:
                    feature_vector = scaler.transform(feature_vector)
                except Exception as e:
                    logger.warning(f"Error applying scaler: {e}. Using unscaled features.")
            
            # Run inference based on model type
            if isinstance(onnx_model, ort.InferenceSession):
                # ONNX model
                inputs = {onnx_model.get_inputs()[0].name: feature_vector}
                outputs = onnx_model.run(None, inputs)
                
                # For isolation forest, -1 is anomaly, 1 is normal
                # Convert to [0, 1] where 1 is anomaly
                if len(outputs) > 0 and len(outputs[0]) > 0:
                    raw_score = outputs[0][0]
                    if isinstance(raw_score, (list, np.ndarray)) and len(raw_score) > 0:
                        raw_score = raw_score[0]  # Handle different output formats
                    
                    # Check if using isolation forest (outputs -1 to 1)
                    if -1 <= raw_score <= 1:
                        # Convert isolation forest score to anomaly score (0-1)
                        anomaly_score = 1.0 - (raw_score + 1) / 2
                    else:
                        # Assume it's already an anomaly score
                        anomaly_score = max(0, min(1, float(raw_score)))
                else:
                    # Fallback
                    anomaly_score = 0.5
            else:
                # Custom model with predict method
                score = onnx_model.predict(feature_vector)[0]
                # Ensure score is in [0, 1] range
                anomaly_score = max(0, min(1, score))
            
            return float(anomaly_score)
            
        except Exception as e:
            logger.error(f"Error running inference: {e}", exc_info=True)
            logger.error(f"Model type: {type(onnx_model)}")
            
            # Fallback to heuristic on error
            if "avg_delay" in features:
                return max(0.1, min(0.9, features["avg_delay"] / 600))
            return 0.5

# API endpoints
@app.get("/scores", response_model=List[AnomalyScore])
async def get_anomaly_scores(
    route_id: Optional[str] = None,
    background_tasks: BackgroundTasks = None
):
    """Get current anomaly scores for subway routes."""
    # Check for model updates in background
    if background_tasks:
        background_tasks.add_task(check_model_updates)
    else:
        check_model_updates()
        
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
            logger.warning("Redis timeout getting routes")
            return []
        except Exception as e:
            logger.error(f"Error getting routes: {e}", exc_info=True)
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
                logger.warning(f"Redis timeout storing score for {route}")
            
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
    threshold: float = Query(0.7, ge=0, le=1),
    background_tasks: BackgroundTasks = None
):
    """Get current anomalies above the threshold."""
    # Get fresh anomaly scores
    scores = await get_anomaly_scores(route_id, background_tasks)
    
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

@app.post("/reload-model")
async def manual_reload_model():
    """Manually reload model after retraining."""
    try:
        reload_model()
        return {"status": "success", "message": "Model reloaded successfully"}
    except Exception as e:
        logger.error(f"Error reloading model: {e}", exc_info=True)
        return {"status": "error", "message": f"Error reloading model: {str(e)}"}

@app.get("/health")
async def health_check(background_tasks: BackgroundTasks = None):
    """Health check endpoint."""
    # Check for model updates in background
    if background_tasks:
        background_tasks.add_task(check_model_updates)
    
    model_status = "not_loaded"
    model_type = "none"
    
    if onnx_model is not None:
        if isinstance(onnx_model, ort.InferenceSession):
            model_status = "loaded"
            model_type = "onnx"
        else:
            model_status = "loaded"
            model_type = "sklearn_pickle"
    
    scaler_status = "loaded" if scaler is not None else "not_loaded"
    feature_cols_status = "loaded" if feature_columns is not None else "not_loaded"
    
    redis_ping = False
    try:
        redis_ping = redis_client.ping()
    except:
        pass
    
    # Get model last modified time in readable format
    last_modified_str = "unknown"
    if model_last_modified:
        last_modified_str = datetime.fromtimestamp(model_last_modified).isoformat()
    
    return {
        "status": "ok",
        "model_status": model_status,
        "model_type": model_type,
        "model_last_modified": last_modified_str,
        "model_last_checked": datetime.fromtimestamp(model_last_checked).isoformat() if model_last_checked > 0 else "never",
        "scaler_status": scaler_status,
        "feature_columns_status": feature_cols_status,
        "feature_count": len(feature_columns) if feature_columns else 0,
        "redis_connected": redis_ping,
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)