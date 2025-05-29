# --- backend/app/ml/features.py ---
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
        
        # Calculate delay
        features["delay_seconds"] = trip_data.get("delay_seconds", 0)
        
        # Calculate headway
        cache_key = f"{features['current_station']}_{features['direction']}"
        features["headway_seconds"] = self._calculate_headway(
            cache_key, features["arrival_time"]
        )
        
        # Calculate dwell time
        if features["arrival_time"] and features["departure_time"]:
            dwell = (features["departure_time"] - features["arrival_time"]).total_seconds()
            features["dwell_time_seconds"] = int(dwell) if dwell > 0 else None
        else:
            features["dwell_time_seconds"] = None
        
        # Update cache
        self._update_cache(cache_key, features)
        
        return features
    
    def _get_line_from_route(self, route_id: str) -> str:
        """Map route ID to line grouping."""
        # Normalize route ID
        route = route_id.upper().strip()
        
        # Direct mapping for most lines
        if route in ["1", "2", "3", "4", "5", "6", "7"]:
            return route
        elif route in ["A", "C", "E"]:
            return route
        elif route in ["B", "D", "F", "M"]:
            return route
        elif route in ["N", "Q", "R", "W"]:
            return route
        elif route in ["J", "Z"]:
            return route
        elif route in ["L", "G"]:
            return route
        elif route == "S" or route == "GS":
            return "S"  # Shuttle
        elif route == "SI":
            return "SI"
        else:
            # Default to the route itself if unknown
            return route.lower()
    
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
        """Compute rolling statistical features with proper window handling."""
        
        # Make a copy to avoid modifying original
        df = positions_df.copy()
        
        # Ensure we have timestamp as index for time-based operations
        if 'timestamp' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
            df = df.set_index('timestamp').sort_index()
        
        # Group by station and direction
        grouped = df.groupby(["current_station", "direction"])
        
        # Calculate rolling statistics
        for col in ["headway_seconds", "dwell_time_seconds", "delay_seconds"]:
            if col in df.columns:
                try:
                    # For time-based rolling, we need DatetimeIndex
                    if isinstance(df.index, pd.DatetimeIndex):
                        # Use 1 hour window
                        df[f"{col}_zscore"] = grouped[col].transform(
                            lambda x: (x - x.rolling('1H', min_periods=1).mean()) / 
                                     (x.rolling('1H', min_periods=1).std() + 1e-7)
                        )
                        
                        df[f"{col}_percentile"] = grouped[col].transform(
                            lambda x: x.rolling('1H', min_periods=1).rank(pct=True)
                        )
                    else:
                        # Fallback to integer window (12 periods = ~1 hour for 5-min intervals)
                        window_size = min(12, len(df))
                        
                        df[f"{col}_zscore"] = grouped[col].transform(
                            lambda x: (x - x.rolling(window_size, min_periods=1).mean()) / 
                                     (x.rolling(window_size, min_periods=1).std() + 1e-7)
                        )
                        
                        df[f"{col}_percentile"] = grouped[col].transform(
                            lambda x: x.rolling(window_size, min_periods=1).rank(pct=True)
                        )
                        
                except Exception as e:
                    # If rolling fails, just use global stats
                    print(f"Warning: Rolling calculation failed for {col}: {e}")
                    mean_val = df[col].mean()
                    std_val = df[col].std() + 1e-7
                    df[f"{col}_zscore"] = (df[col] - mean_val) / std_val
                    df[f"{col}_percentile"] = df[col].rank(pct=True)
        
        # Reset index if we set it
        if isinstance(df.index, pd.DatetimeIndex) and 'timestamp' not in df.columns:
            df = df.reset_index()
        
        return df
    
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