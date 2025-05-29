"""
Feature extraction for subway time-series data.
Computes headway, dwell time, schedule adherence, and rolling statistics.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats


class FeatureExtractor:
    """Extract ML features from raw GTFS-RT data."""
    
    def __init__(self, headway_window_minutes: int = 30, rolling_hours: int = 1):
        self.headway_window = timedelta(minutes=headway_window_minutes)
        self.rolling_window = timedelta(hours=rolling_hours)
        
        # Cache for previous trains
        self.train_cache: Dict[str, List[Dict]] = {}
    
    def extract_trip_features(self, trip_data: Dict, feed_id: str) -> Optional[Dict]:
        """Extract features from single trip update."""
        
        # Basic fields
        features = {
            "trip_id": trip_data["trip_id"],
            "route_id": trip_data["route_id"],
            "line": self._get_line_from_route(trip_data["route_id"]),
            "direction": trip_data.get("direction", 0),
            "current_station": trip_data.get("stop_id"),
            "arrival_time": trip_data.get("arrival_time"),
            "departure_time": trip_data.get("departure_time"),
            "timestamp": datetime.utcnow(),
        }
        
        # Calculate delay if scheduled time available
        if "scheduled_arrival" in trip_data and features["arrival_time"]:
            delay = (features["arrival_time"] - trip_data["scheduled_arrival"]).total_seconds()
            features["delay_seconds"] = int(delay)
        else:
            features["delay_seconds"] = 0
        
        # Calculate headway
        cache_key = f"{features['current_station']}_{features['direction']}"
        features["headway_seconds"] = self._calculate_headway(
            cache_key, features["arrival_time"]
        )
        
        # Calculate dwell time
        if features["arrival_time"] and features["departure_time"]:
            dwell = (features["departure_time"] - features["arrival_time"]).total_seconds()
            features["dwell_time_seconds"] = int(dwell)
        
        # Update cache
        self._update_cache(cache_key, features)
        
        return features
    
    def _get_line_from_route(self, route_id: str) -> str:
        """Map route ID to line grouping."""
        # Handle express/local variants
        route_map = {
            "6X": "6",
            "7X": "7",
            "Q": "nqrw",
            "N": "nqrw",
            "R": "nqrw",
            "W": "nqrw",
            # Add more mappings as needed
        }
        
        return route_map.get(route_id, route_id.lower())
    
    def _calculate_headway(self, cache_key: str, arrival_time: Optional[datetime]) -> Optional[int]:
        """Calculate time since previous train at same station/direction."""
        if not arrival_time:
            return None
        
        previous_trains = self.train_cache.get(cache_key, [])
        if not previous_trains:
            return None
        
        # Find most recent train within window
        for prev in reversed(previous_trains):
            if prev["arrival_time"] and arrival_time - prev["arrival_time"] < self.headway_window:
                return int((arrival_time - prev["arrival_time"]).total_seconds())
        
        return None
    
    def _update_cache(self, cache_key: str, features: Dict):
        """Update rolling cache of recent trains."""
        if cache_key not in self.train_cache:
            self.train_cache[cache_key] = []
        
        self.train_cache[cache_key].append(features)
        
        # Remove old entries
        cutoff = datetime.utcnow() - self.headway_window
        self.train_cache[cache_key] = [
            t for t in self.train_cache[cache_key]
            if t["timestamp"] > cutoff
        ]
    
    def compute_rolling_features(self, positions_df: pd.DataFrame) -> pd.DataFrame:
        """Compute rolling statistical features."""
        
        # Group by station and direction
        grouped = positions_df.groupby(["current_station", "direction"])
        
        # Rolling statistics
        for col in ["headway_seconds", "dwell_time_seconds", "delay_seconds"]:
            if col in positions_df.columns:
                # Z-score within rolling window
                positions_df[f"{col}_zscore"] = grouped[col].transform(
                    lambda x: (x - x.rolling("1H").mean()) / x.rolling("1H").std()
                )
                
                # Percentile rank
                positions_df[f"{col}_percentile"] = grouped[col].transform(
                    lambda x: x.rolling("1H").rank(pct=True)
                )
        
        return positions_df
    
    def create_station_features(self, station_id: str, num_stations: int = 472) -> np.ndarray:
        """Create one-hot encoded station features."""
        # In production, would map station_id to index
        # For now, simple hash-based index
        station_idx = hash(station_id) % num_stations
        
        features = np.zeros(num_stations)
        features[station_idx] = 1
        
        return features
    
    def create_temporal_features(self, timestamp: datetime) -> Dict[str, float]:
        """Extract temporal features from timestamp."""
        return {
            "hour": timestamp.hour,
            "day_of_week": timestamp.weekday(),
            "is_weekend": timestamp.weekday() >= 5,
            "is_rush_hour": self._is_rush_hour(timestamp),
            "minutes_since_midnight": timestamp.hour * 60 + timestamp.minute,
        }
    
    def _is_rush_hour(self, timestamp: datetime) -> bool:
        """Determine if time is during rush hour."""
        hour = timestamp.hour
        is_weekday = timestamp.weekday() < 5
        
        morning_rush = 7 <= hour <= 10
        evening_rush = 17 <= hour <= 20
        
        return is_weekday and (morning_rush or evening_rush)