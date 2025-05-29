"""
Feature extraction for subway time-series data.
Updated with new Pandas frequency aliases (2.2.0+).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
import re

import numpy as np
import pandas as pd
from scipy import stats

from app.config import get_settings

settings = get_settings()


class FeatureExtractor:
    """Extract ML features from raw GTFS-RT data."""
    
    def __init__(self, headway_window_minutes: int = 30, rolling_hours: int = 1):
        self.headway_window = timedelta(minutes=headway_window_minutes)
        self.rolling_window = timedelta(hours=rolling_hours)
        
        # Cache for previous trains
        self.train_cache: Dict[str, List[Dict]] = {}
        
        # Updated frequency mappings
        self.freq_mapping = {
            'H': 'h',      # Hourly
            'T': 'min',    # Minutely  
            'S': 's',      # Secondly
            'L': 'ms',     # Milliseconds
            'U': 'us',     # Microseconds
            'N': 'ns',     # Nanoseconds
            'D': 'D',      # Daily (unchanged)
            'W': 'W',      # Weekly (unchanged)
            'M': 'ME',     # Month end
            'MS': 'MS',    # Month start
            'Q': 'QE',     # Quarter end
            'QS': 'QS',    # Quarter start
            'Y': 'YE',     # Year end
            'YS': 'YS',    # Year start
            'A': 'YE',     # Year end (alias)
            'AS': 'YS',    # Year start (alias)
        }
    
    def update_frequency_alias(self, freq_str: str) -> str:
        """Update deprecated frequency aliases to current standards."""
        updated = freq_str
        
        for old, new in self.freq_mapping.items():
            # Handle numeric prefixes (e.g., "3H" -> "3h")
            pattern = r'(\d*)' + re.escape(old) + r'(?![a-zA-Z])'
            updated = re.sub(pattern, r'\1' + new, updated)
        
        return updated
    
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
            return "S"
        elif route == "SI":
            return "SI"
        else:
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
        """Compute rolling statistical features with updated Pandas frequencies."""
        
        df = positions_df.copy()
        
        # Ensure we have timestamp as index
        if 'timestamp' in df.columns and not isinstance(df.index, pd.DatetimeIndex):
            df = df.set_index('timestamp').sort_index()
        
        # Group by station and direction
        grouped = df.groupby(["current_station", "direction"])
        
        # Calculate rolling statistics with updated frequencies
        for col in ["headway_seconds", "dwell_time_seconds", "delay_seconds"]:
            if col in df.columns:
                try:
                    # Use new frequency alias '1h' instead of '1H'
                    window = self.update_frequency_alias('1H')  # converts to '1h'
                    
                    # Z-score calculation
                    df[f"{col}_zscore"] = grouped[col].transform(
                        lambda x: (x - x.rolling(window, min_periods=1).mean()) / 
                                 (x.rolling(window, min_periods=1).std() + 1e-7)
                    )
                    
                    # Percentile calculation
                    df[f"{col}_percentile"] = grouped[col].transform(
                        lambda x: x.rolling(window, min_periods=1).rank(pct=True)
                    )
                    
                    # Additional rolling features with various windows
                    for hrs in [3, 6, 12, 24]:
                        win = self.update_frequency_alias(f'{hrs}H')  # e.g., '3H' -> '3h'
                        
                        df[f"{col}_rolling_{hrs}h_mean"] = grouped[col].transform(
                            lambda x: x.rolling(win, min_periods=1).mean()
                        )
                        
                        df[f"{col}_rolling_{hrs}h_std"] = grouped[col].transform(
                            lambda x: x.rolling(win, min_periods=1).std()
                        )
                        
                except Exception as e:
                    # Fallback to simple calculations if rolling fails
                    print(f"Warning: Rolling calculation failed for {col}: {e}")
                    mean_val = df[col].mean()
                    std_val = df[col].std() + 1e-7
                    df[f"{col}_zscore"] = (df[col] - mean_val) / std_val
                    df[f"{col}_percentile"] = df[col].rank(pct=True)
        
        # Reset index if we set it
        if isinstance(df.index, pd.DatetimeIndex) and 'timestamp' not in df.columns:
            df = df.reset_index()
        
        return df
    
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
    
    def create_station_features(self, station_id: str, num_stations: int = 472) -> np.ndarray:
        """Create one-hot encoded station features."""
        station_idx = hash(station_id) % num_stations
        
        features = np.zeros(num_stations)
        features[station_idx] = 1
        
        return features