"""Test feature extraction logic."""

import pytest
from datetime import datetime, timedelta
import pandas as pd

from app.ml.features import FeatureExtractor


class TestFeatureExtractor:
    """Test feature extraction functionality."""

    @pytest.fixture
    def extractor(self):
        """Create feature extractor instance."""
        return FeatureExtractor(headway_window_minutes=30, rolling_hours=1)

    def test_extract_trip_features(self, extractor):
        """Test basic feature extraction from trip data."""
        trip_data = {
            "trip_id": "test_trip_1",
            "route_id": "6",
            "direction": 1,
            "stop_id": "635N",
            "arrival_time": datetime.utcnow(),
            "departure_time": datetime.utcnow() + timedelta(seconds=30),
        }
        
        features = extractor.extract_trip_features(trip_data, "123456")
        
        assert features["trip_id"] == "test_trip_1"
        assert features["route_id"] == "6"
        assert features["dwell_time_seconds"] == 30
        assert features["line"] == "6"

    def test_calculate_headway(self, extractor):
        """Test headway calculation between trains."""
        # First train
        trip1 = {
            "trip_id": "trip_1",
            "route_id": "6",
            "stop_id": "635N",
            "arrival_time": datetime.utcnow() - timedelta(minutes=5),
            "departure_time": datetime.utcnow() - timedelta(minutes=4, seconds=30),
        }
        
        # Process first train
        extractor.extract_trip_features(trip1, "123456")
        
        # Second train at same station
        trip2 = {
            "trip_id": "trip_2",
            "route_id": "6",
            "stop_id": "635N",
            "arrival_time": datetime.utcnow(),
            "departure_time": datetime.utcnow() + timedelta(seconds=30),
        }
        
        features = extractor.extract_trip_features(trip2, "123456")
        
        # Should have 5 minute headway
        assert features["headway_seconds"] == pytest.approx(300, rel=1)

    def test_temporal_features(self, extractor):
        """Test temporal feature extraction."""
        # Monday at 8 AM (rush hour)
        monday_rush = datetime(2025, 1, 6, 8, 0, 0)
        features = extractor.create_temporal_features(monday_rush)
        
        assert features["hour"] == 8
        assert features["day_of_week"] == 0  # Monday
        assert features["is_weekend"] is False
        assert features["is_rush_hour"] is True
        
        # Saturday at 2 PM (not rush hour)
        saturday_afternoon = datetime(2025, 1, 11, 14, 0, 0)
        features = extractor.create_temporal_features(saturday_afternoon)
        
        assert features["day_of_week"] == 5  # Saturday
        assert features["is_weekend"] is True
        assert features["is_rush_hour"] is False