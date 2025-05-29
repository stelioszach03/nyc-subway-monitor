"""
Isolation Forest implementation for unsupervised anomaly detection.
Fast baseline model for multivariate time-series anomalies.
"""

import json
import pickle
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.config import get_settings

settings = get_settings()


class IsolationForestDetector:
    """Isolation Forest for subway anomaly detection."""
    
    def __init__(self, contamination: float = None):
        self.contamination = contamination or settings.anomaly_contamination
        self.model = None
        self.scaler = StandardScaler()
        self.feature_columns = []
        self.version = None
        
    def prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """Prepare features for training/inference."""
        
        # Select numerical features
        feature_cols = [
            "headway_seconds",
            "dwell_time_seconds", 
            "delay_seconds",
            "hour",
            "day_of_week",
            "is_rush_hour",
        ]
        
        # Add computed features if available
        for col in df.columns:
            if col.endswith("_zscore") or col.endswith("_percentile"):
                feature_cols.append(col)
        
        # Filter to available columns
        self.feature_columns = [col for col in feature_cols if col in df.columns]
        
        # Handle missing values
        X = df[self.feature_columns].fillna(0)
        
        return X.values
    
    def train(self, train_data: pd.DataFrame) -> Dict[str, float]:
        """Train Isolation Forest on historical data."""
        
        # Prepare features
        X = self.prepare_features(train_data)
        
        # Fit scaler
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model = IsolationForest(
            contamination=self.contamination,
            random_state=42,
            n_estimators=100,
            max_samples="auto",
            n_jobs=-1,
        )
        
        self.model.fit(X_scaled)
        
        # Calculate metrics on training data
        predictions = self.model.predict(X_scaled)
        anomaly_scores = self.model.score_samples(X_scaled)
        
        metrics = {
            "train_samples": len(X),
            "anomaly_rate": (predictions == -1).mean(),
            "score_mean": float(anomaly_scores.mean()),
            "score_std": float(anomaly_scores.std()),
            "score_threshold": float(np.percentile(anomaly_scores, self.contamination * 100)),
        }
        
        # Set version
        self.version = f"if_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        return metrics
    
    def predict(self, data: pd.DataFrame) -> List[Dict]:
        """Detect anomalies in new data."""
        
        if self.model is None:
            raise ValueError("Model not trained")
        
        # Prepare features
        X = self.prepare_features(data)
        X_scaled = self.scaler.transform(X)
        
        # Get predictions and scores
        predictions = self.model.predict(X_scaled)
        scores = self.model.score_samples(X_scaled)
        
        # Normalize scores to 0-1 range
        min_score = self.model.score_samples(X_scaled).min()
        max_score = 0  # Maximum possible score
        normalized_scores = (scores - min_score) / (max_score - min_score)
        
        # Collect anomalies
        anomalies = []
        
        for idx, (pred, score) in enumerate(zip(predictions, normalized_scores)):
            if pred == -1:  # Anomaly
                row = data.iloc[idx]
                
                anomaly = {
                    "station_id": row.get("current_station"),
                    "line": row.get("line"),
                    "anomaly_type": self._determine_anomaly_type(row),
                    "severity": float(1 - score),  # Higher score = more anomalous
                    "model_name": "isolation_forest",
                    "model_version": self.version,
                    "features": {
                        col: float(row[col]) for col in self.feature_columns
                        if not pd.isna(row[col])
                    },
                    "metadata": {
                        "trip_id": row.get("trip_id"),
                        "route_id": row.get("route_id"),
                        "timestamp": row.get("timestamp").isoformat() if pd.notna(row.get("timestamp")) else None,
                    }
                }
                
                anomalies.append(anomaly)
        
        return anomalies
    
    def _determine_anomaly_type(self, row: pd.Series) -> str:
        """Determine primary anomaly type based on features."""
        
        # Check which feature is most anomalous
        anomaly_types = []
        
        if "headway_seconds_zscore" in row and abs(row["headway_seconds_zscore"]) > 2:
            anomaly_types.append("headway")
        
        if "dwell_time_seconds_zscore" in row and abs(row["dwell_time_seconds_zscore"]) > 2:
            anomaly_types.append("dwell")
        
        if "delay_seconds" in row and abs(row["delay_seconds"]) > 300:  # 5+ minutes
            anomaly_types.append("delay")
        
        if anomaly_types:
            return "_".join(anomaly_types)
        else:
            return "combined"
    
    def save(self, path: Path):
        """Save model artifacts."""
        path.mkdir(parents=True, exist_ok=True)
        
        # Save model
        with open(path / "model.pkl", "wb") as f:
            pickle.dump(self.model, f)
        
        # Save scaler
        with open(path / "scaler.pkl", "wb") as f:
            pickle.dump(self.scaler, f)
        
        # Save metadata
        metadata = {
            "version": self.version,
            "contamination": self.contamination,
            "feature_columns": self.feature_columns,
            "trained_at": datetime.utcnow().isoformat(),
        }
        
        with open(path / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
    
    def load(self, path: Path):
        """Load model artifacts."""
        
        # Load model
        with open(path / "model.pkl", "rb") as f:
            self.model = pickle.load(f)
        
        # Load scaler  
        with open(path / "scaler.pkl", "rb") as f:
            self.scaler = pickle.load(f)
        
        # Load metadata
        with open(path / "metadata.json", "r") as f:
            metadata = json.load(f)
            self.version = metadata["version"]
            self.contamination = metadata["contamination"]
            self.feature_columns = metadata["feature_columns"]