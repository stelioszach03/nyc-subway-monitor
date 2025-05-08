# nyc-subway-monitor/services/ml/train.py
import os
import pickle
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import onnxmltools
from sqlalchemy import create_engine

# Configuration
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "timescaledb")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "subway")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "subway_password")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "subway_monitor")
MODEL_OUTPUT_PATH = os.environ.get("MODEL_OUTPUT_PATH", "/app/models/anomaly_model.onnx")

def get_training_data() -> pd.DataFrame:
    """Fetch historical delay data from TimescaleDB."""
    # Connect to database
    db_url = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    engine = create_engine(db_url)
    
    # Get data from the last 7 days
    end_date = datetime.now()
    start_date = end_date - timedelta(days=7)
    
    # Query historical delay data
    query = f"""
    SELECT 
        route_id,
        avg_delay,
        max_delay,
        min_delay,
        train_count,
        window_start,
        window_end
    FROM train_delays
    WHERE window_end BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
    ORDER BY window_end
    """
    
    # Load data into DataFrame
    df = pd.read_sql(query, engine)
    return df

def preprocess_data(df: pd.DataFrame) -> Tuple[Dict[str, pd.DataFrame], Dict[str, StandardScaler]]:
    """Preprocess data for anomaly detection."""
    # Group by route_id
    route_groups = {route: group for route, group in df.groupby('route_id')}
    
    # Create feature datasets for each route
    route_features = {}
    route_scalers = {}
    
    for route, data in route_groups.items():
        # Compute additional features
        data['hour_of_day'] = data['window_end'].dt.hour
        data['day_of_week'] = data['window_end'].dt.dayofweek
        data['delay_per_train'] = data['avg_delay'] / data['train_count'].clip(lower=1)
        
        # Aggregate to 15-minute windows
        data['window_bin'] = data['window_end'].dt.floor('15min')
        agg_data = data.groupby('window_bin').agg({
            'avg_delay': 'mean',
            'max_delay': 'max',
            'min_delay': 'min',
            'train_count': 'mean',
            'hour_of_day': 'first',
            'day_of_week': 'first',
            'delay_per_train': 'mean'
        }).reset_index()
        
        # Standard scale numerical features
        feature_cols = ['avg_delay', 'max_delay', 'min_delay', 'train_count', 'delay_per_train']
        scaler = StandardScaler()
        agg_data[feature_cols] = scaler.fit_transform(agg_data[feature_cols])
        
        route_features[route] = agg_data
        route_scalers[route] = scaler
    
    return route_features, route_scalers

def train_model(route_features: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """Train isolation forest models for each route."""
    models = {}
    
    for route, features in route_features.items():
        if len(features) < 10:  # Skip routes with insufficient data
            continue
            
        # Select feature columns
        X = features[['avg_delay', 'max_delay', 'min_delay', 'train_count', 'delay_per_train']].values
        
        # Train isolation forest
        model = IsolationForest(
            n_estimators=100,
            max_samples='auto',
            contamination=0.05,  # Assume 5% of data points are anomalies
            random_state=42
        )
        
        model.fit(X)
        models[route] = model
    
    return models

def export_to_onnx(models: Dict[str, Any], scalers: Dict[str, StandardScaler]) -> None:
    """Export trained models to ONNX format."""
    # Ensure output directory exists
    os.makedirs(os.path.dirname(MODEL_OUTPUT_PATH), exist_ok=True)
    
    # We'll create a feature schema for ONNX conversion
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    
    # Choose a representative model (first one)
    if not models:
        print("No models to export!")
        return
        
    # Get a sample route
    sample_route = list(models.keys())[0]
    model = models[sample_route]
    
    # Define input feature schema
    input_type = [('features', FloatTensorType([None, 6]))]  # 6 features
    
    # Convert model to ONNX
    onnx_model = convert_sklearn(model, 'subway_anomaly_model', input_type)
    
    # Save ONNX model
    with open(MODEL_OUTPUT_PATH, "wb") as f:
        f.write(onnx_model.SerializeToString())
    
    # Save scalers for each route
    scalers_path = os.path.join(os.path.dirname(MODEL_OUTPUT_PATH), "scalers.pkl")
    with open(scalers_path, "wb") as f:
        pickle.dump(scalers, f)
    
    print(f"Model exported to {MODEL_OUTPUT_PATH}")
    print(f"Scalers exported to {scalers_path}")

def main():
    """Main training function."""
    print("Starting anomaly detection model training...")
    
    # Get training data
    print("Fetching training data...")
    df = get_training_data()
    
    if df.empty:
        print("No training data available. Exiting.")
        return
    
    print(f"Retrieved {len(df)} records for training.")
    
    # Preprocess data
    print("Preprocessing data...")
    route_features, route_scalers = preprocess_data(df)
    
    # Train models
    print("Training models...")
    models = train_model(route_features)
    
    # Export to ONNX
    print("Exporting models to ONNX...")
    export_to_onnx(models, route_scalers)
    
    print("Training complete!")

if __name__ == "__main__":
    main()