"""
Real-time anomaly detection using trained models.
Combines predictions from multiple models for ensemble detection.
"""

from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd
import structlog

from app.ml.models.isolation_forest import IsolationForestDetector
from app.ml.models.lstm_autoencoder import LSTMDetector

logger = structlog.get_logger()


class AnomalyDetector:
    """Ensemble anomaly detector combining multiple models."""
    
    def __init__(self):
        self.models: Dict[str, any] = {}
        self.last_run_time: Optional[datetime] = None
        
    def register_model(self, name: str, model: any):
        """Register a model for ensemble detection."""
        self.models[name] = model
        logger.info(f"Registered model: {name}")
        
    def is_model_loaded(self, model_type: str) -> bool:
        """Check if a model type is loaded."""
        return model_type in self.models
    
    async def detect_anomalies(self, positions: List[any]) -> List[Dict]:
        """Run anomaly detection on train positions."""
        
        if not positions:
            return []
        
        # Convert to DataFrame
        df = pd.DataFrame([
            {
                "id": p.id,
                "timestamp": p.timestamp,
                "trip_id": p.trip_id,
                "route_id": p.route_id,
                "line": p.line,
                "current_station": p.current_station,
                "headway_seconds": p.headway_seconds,
                "dwell_time_seconds": p.dwell_time_seconds,
                "delay_seconds": p.delay_seconds,
                "direction": p.direction,
            }
            for p in positions
        ])
        
        # Add temporal features
        df["hour"] = df["timestamp"].dt.hour
        df["day_of_week"] = df["timestamp"].dt.dayofweek
        df["is_rush_hour"] = df["timestamp"].apply(self._is_rush_hour)
        
        all_anomalies = []
        
        # Run each model
        for model_name, model in self.models.items():
            try:
                if isinstance(model, IsolationForestDetector):
                    anomalies = model.predict(df)
                elif isinstance(model, LSTMDetector):
                    anomalies = model.predict(df)
                else:
                    continue
                
                # Add source position ID for tracking
                for anomaly in anomalies:
                    anomaly["source_position_ids"] = [df.iloc[i]["id"] for i in range(len(df))]
                
                all_anomalies.extend(anomalies)
                
                logger.info(f"Model {model_name} detected {len(anomalies)} anomalies")
                
            except Exception as e:
                logger.error(f"Error in model {model_name}: {e}")
        
        # Deduplicate and combine anomalies
        combined_anomalies = self._combine_anomalies(all_anomalies)
        
        self.last_run_time = datetime.utcnow()
        
        return combined_anomalies
    
    def _is_rush_hour(self, timestamp: pd.Timestamp) -> bool:
        """Check if timestamp is during rush hour."""
        hour = timestamp.hour
        is_weekday = timestamp.weekday() < 5
        
        morning_rush = 7 <= hour <= 10
        evening_rush = 17 <= hour <= 20
        
        return is_weekday and (morning_rush or evening_rush)
    
    def _combine_anomalies(self, anomalies: List[Dict]) -> List[Dict]:
        """Combine anomalies from multiple models."""
        
        # Group by station and time window
        from collections import defaultdict
        grouped = defaultdict(list)
        
        for anomaly in anomalies:
            # Create key for grouping (station + 5-minute window)
            key = (
                anomaly.get("station_id"),
                anomaly.get("line"),
                # Round to 5-minute window
                pd.Timestamp(anomaly["metadata"].get("timestamp", datetime.utcnow())).floor("5min")
                if "timestamp" in anomaly.get("metadata", {})
                else None
            )
            grouped[key].append(anomaly)
        
        # Combine grouped anomalies
        combined = []
        
        for key, group in grouped.items():
            if len(group) == 1:
                # Single model detection
                combined.append(group[0])
            else:
                # Multiple models detected - combine
                severity_scores = [a["severity"] for a in group]
                models = [a["model_name"] for a in group]
                
                combined_anomaly = {
                    "station_id": key[0],
                    "line": key[1],
                    "anomaly_type": "ensemble",
                    "severity": max(severity_scores),  # Take maximum severity
                    "model_name": "ensemble",
                    "model_version": f"ensemble_{len(models)}",
                    "features": group[0]["features"],  # Use first model's features
                    "metadata": {
                        "models": models,
                        "individual_severities": dict(zip(models, severity_scores)),
                        "detection_count": len(group),
                    }
                }
                
                combined.append(combined_anomaly)
        
        return combined
    
    def get_model_stats(self) -> Dict:
        """Get statistics about loaded models."""
        return {
            "loaded_models": list(self.models.keys()),
            "model_count": len(self.models),
            "last_run": self.last_run_time.isoformat() if self.last_run_time else None,
        }