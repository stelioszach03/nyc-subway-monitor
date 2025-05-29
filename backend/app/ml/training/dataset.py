"""
Dataset utilities for model training.
Handles data loading, preprocessing, and batching.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset

from app.db.models import TrainPosition


class SubwayDataset:
    """Base dataset class for subway anomaly detection."""
    
    def __init__(self, data: pd.DataFrame, target_col: Optional[str] = None):
        self.data = data
        self.target_col = target_col
        self._prepare_data()
    
    def _prepare_data(self):
        """Prepare data for training."""
        # Sort by timestamp
        self.data = self.data.sort_values('timestamp')
        
        # Handle missing values
        numeric_cols = self.data.select_dtypes(include=[np.number]).columns
        self.data[numeric_cols] = self.data[numeric_cols].fillna(0)
        
        # Remove outliers (optional)
        for col in ['headway_seconds', 'dwell_time_seconds', 'delay_seconds']:
            if col in self.data.columns:
                # Cap at 99th percentile
                cap_value = self.data[col].quantile(0.99)
                self.data[col] = self.data[col].clip(upper=cap_value)
    
    def split(self, test_size: float = 0.2, random_state: int = 42) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Split data into train and test sets."""
        # For time series, use temporal split
        split_idx = int(len(self.data) * (1 - test_size))
        
        train_data = self.data.iloc[:split_idx]
        test_data = self.data.iloc[split_idx:]
        
        return train_data, test_data
    
    def get_feature_columns(self) -> List[str]:
        """Get list of feature columns."""
        exclude_cols = ['timestamp', 'id', 'trip_id', 'route_id', 'line', 
                       'current_station', 'next_station', 'arrival_time', 
                       'departure_time']
        
        if self.target_col:
            exclude_cols.append(self.target_col)
        
        feature_cols = [col for col in self.data.columns if col not in exclude_cols]
        return feature_cols
    
    def to_numpy(self) -> Tuple[np.ndarray, Optional[np.ndarray]]:
        """Convert to numpy arrays."""
        feature_cols = self.get_feature_columns()
        X = self.data[feature_cols].values
        
        y = None
        if self.target_col and self.target_col in self.data.columns:
            y = self.data[self.target_col].values
        
        return X, y


class WindowedDataset(Dataset):
    """PyTorch dataset for windowed time series data."""
    
    def __init__(self, data: np.ndarray, window_size: int, stride: int = 1):
        self.data = data
        self.window_size = window_size
        self.stride = stride
        
        # Calculate number of windows
        self.n_windows = (len(data) - window_size) // stride + 1
    
    def __len__(self):
        return self.n_windows
    
    def __getitem__(self, idx):
        start_idx = idx * self.stride
        end_idx = start_idx + self.window_size
        
        window = self.data[start_idx:end_idx]
        return window.astype(np.float32)


def create_anomaly_labels(df: pd.DataFrame, method: str = 'isolation_forest') -> pd.Series:
    """Create synthetic anomaly labels for evaluation."""
    from sklearn.ensemble import IsolationForest
    
    if method == 'isolation_forest':
        # Use Isolation Forest to create labels
        feature_cols = ['headway_seconds', 'dwell_time_seconds', 'delay_seconds']
        feature_cols = [col for col in feature_cols if col in df.columns]
        
        if not feature_cols:
            # Fallback to random labels
            return pd.Series(np.random.choice([0, 1], size=len(df), p=[0.95, 0.05]))
        
        X = df[feature_cols].fillna(0).values
        
        clf = IsolationForest(contamination=0.05, random_state=42)
        labels = clf.fit_predict(X)
        
        # Convert to 0/1 (0=normal, 1=anomaly)
        return pd.Series(labels).map({1: 0, -1: 1})
    
    else:
        raise ValueError(f"Unknown method: {method}")


def load_training_data(
    positions: List[TrainPosition],
    lookback_days: int = 7
) -> pd.DataFrame:
    """Load and prepare training data from database records."""
    
    # Convert to DataFrame
    data = []
    for pos in positions:
        data.append({
            'timestamp': pos.timestamp,
            'trip_id': pos.trip_id,
            'route_id': pos.route_id,
            'line': pos.line,
            'direction': pos.direction,
            'current_station': pos.current_station,
            'headway_seconds': pos.headway_seconds,
            'dwell_time_seconds': pos.dwell_time_seconds,
            'delay_seconds': pos.delay_seconds,
        })
    
    df = pd.DataFrame(data)
    
    # Add temporal features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
    
    # Add rolling statistics
    for col in ['headway_seconds', 'dwell_time_seconds', 'delay_seconds']:
        if col in df.columns:
            df[f'{col}_rolling_mean'] = df.groupby('current_station')[col].transform(
                lambda x: x.rolling('1H', min_periods=1).mean()
            )
            df[f'{col}_rolling_std'] = df.groupby('current_station')[col].transform(
                lambda x: x.rolling('1H', min_periods=1).std()
            )
    
    return df


def augment_anomalies(df: pd.DataFrame, augmentation_factor: float = 2.0) -> pd.DataFrame:
    """Augment anomaly samples to handle class imbalance."""
    
    if 'is_anomaly' not in df.columns:
        return df
    
    normal_samples = df[df['is_anomaly'] == 0]
    anomaly_samples = df[df['is_anomaly'] == 1]
    
    if len(anomaly_samples) == 0:
        return df
    
    # Oversample anomalies
    n_augment = int(len(anomaly_samples) * (augmentation_factor - 1))
    augmented = anomaly_samples.sample(n=n_augment, replace=True, random_state=42)
    
    # Add noise to augmented samples
    numeric_cols = augmented.select_dtypes(include=[np.number]).columns
    noise = np.random.normal(0, 0.1, size=(len(augmented), len(numeric_cols)))
    augmented[numeric_cols] = augmented[numeric_cols] + noise
    
    # Combine all samples
    result = pd.concat([normal_samples, anomaly_samples, augmented], ignore_index=True)
    
    return result.sample(frac=1, random_state=42).reset_index(drop=True)