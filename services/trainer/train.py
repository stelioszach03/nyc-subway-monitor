# services/trainer/train.py

import os
import json
import pickle
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sqlalchemy import create_engine, text
import requests
import logging
import time
import traceback
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("model_trainer")

# ONNX support with graceful fallback
try:
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False
    logger.warning("ONNX export not available. Using pickle format instead.")

# Configuration from environment variables
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "timescaledb")
POSTGRES_PORT = os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "subway")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "subway_password")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "subway_monitor")
ML_SERVICE_URL = os.environ.get("ML_SERVICE_URL", "http://ml:8000")

# Model output path
MODEL_OUTPUT_PATH = os.environ.get("MODEL_OUTPUT_PATH", "/app/models/anomaly_model.onnx")
MODEL_DIR = os.path.dirname(MODEL_OUTPUT_PATH)

def get_db_connection():
    """Create and return a database connection with retry logic."""
    db_url = (
        f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}"
        f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )
    
    max_retries = 5
    for attempt in range(max_retries):
        try:
            logger.info(f"Connecting to database (attempt {attempt+1}/{max_retries})...")
            engine = create_engine(db_url, pool_timeout=30, connect_args={"connect_timeout": 10})
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection successful")
            return engine
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                logger.warning(f"Database connection failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.error(f"Database connection failed after {max_retries} attempts: {e}")
                raise

def get_historical_data():
    """Get historical data for training with improved error handling."""
    try:
        engine = get_db_connection()
        
        end_date = datetime.now()
        # Use more data for better training - 14 days
        start_date = end_date - timedelta(days=14)
        logger.info(f"Fetching data from {start_date} to {end_date}...")
        
        query = f"""
        SELECT
            route_id,
            timestamp,
            latitude,
            longitude,
            delay,
            current_status,
            vehicle_id
        FROM train_history
        WHERE timestamp BETWEEN '{start_date.isoformat()}' AND '{end_date.isoformat()}'
          AND delay IS NOT NULL
        ORDER BY timestamp
        """
        
        df = pd.read_sql(query, engine)
        logger.info(f"Retrieved {len(df)} records")
        
        if df.empty or len(df) < 50:  # Minimum threshold for real data
            logger.warning("Insufficient historical data. Creating synthetic data for initial training...")
            df = create_synthetic_data()
        
        return df
    except Exception as e:
        logger.error(f"Error getting historical data: {e}")
        logger.error(traceback.format_exc())
        logger.warning("Falling back to synthetic data generation...")
        return create_synthetic_data()

def create_synthetic_data():
    """Create synthetic data for initial model training."""
    logger.info("Generating synthetic training data...")
    
    # Create synthetic data for all subway lines
    dummy_data = []
    routes = ['1','2','3','4','5','6','7','A','C','E','B','D','F','M','G','J','Z','L','N','Q','R','W','S']
    
    # Generate 2000 data points
    for i in range(2000):
        route = routes[i % len(routes)]
        
        # Different delay patterns for different lines
        if route in ['A', 'C', 'E', '4', '5', '6']:  # Lines with typically higher delays
            delay = np.random.normal(120, 60)
        else:  # More reliable lines
            delay = np.random.normal(45, 30)
            
        # Some trains with no delay
        if np.random.random() < 0.2:
            delay = np.random.normal(5, 10)
            
        # Negative delays (early trains) rarely occur
        if np.random.random() < 0.05:
            delay = -np.random.normal(30, 15)
            
        # Extremely rare large delays (anomalies)
        if np.random.random() < 0.02:
            delay = np.random.normal(600, 120)
            
        timestamp = datetime.now() - timedelta(minutes=30*i % 1440)  # Distribute over 24 hours
        
        dummy_data.append({
            'route_id': route,
            'timestamp': timestamp,
            'latitude': 40.7589 + np.random.normal(0, 0.1),
            'longitude': -73.9851 + np.random.normal(0, 0.1),
            'delay': max(-120, delay),  # Limit negative delays
            'current_status': np.random.choice(['STOPPED_AT', 'IN_TRANSIT_TO']),
            'vehicle_id': f"{route}_{i % 30}"  # Simulate different vehicles
        })
        
    df = pd.DataFrame(dummy_data)
    logger.info(f"Generated {len(df)} synthetic records for initial training")
    return df

def extract_features(df):
    """Extract features for anomaly detection with improved processing."""
    logger.info("Extracting features...")
    
    # Ensure timestamp is datetime
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Add time features
    df['hour'] = df['timestamp'].dt.hour
    df['day_of_week'] = df['timestamp'].dt.dayofweek
    df['is_weekend'] = df['day_of_week'].isin([5,6]).astype(int)
    df['time_bucket'] = df['timestamp'].dt.floor('5min')
    
    # Add part of day feature - important for transit patterns
    df['part_of_day'] = pd.cut(
        df['hour'], 
        bins=[0, 6, 10, 15, 19, 24], 
        labels=['night', 'morning_rush', 'midday', 'evening_rush', 'evening']
    )
    
    # Group data by route, time window, and part of day
    # to account for periodic patterns
    try:
        agg = df.groupby(['route_id', 'time_bucket', 'part_of_day']).agg({
            'delay': ['mean', 'std', 'max', 'min', 'count'],
            'hour': 'first',
            'day_of_week': 'first',
            'is_weekend': 'first',
            'vehicle_id': 'nunique'  # Number of unique vehicles
        }).reset_index()
        
        # Flatten the columns
        agg.columns = ['_'.join(col).rstrip('_') for col in agg.columns]
        
        # Rename columns for easier reference
        rename_dict = {
            'delay_mean': 'avg_delay',
            'delay_std': 'delay_std',
            'delay_max': 'max_delay',
            'delay_min': 'min_delay',
            'delay_count': 'train_count',
            'hour_first': 'hour',
            'day_of_week_first': 'day_of_week',
            'is_weekend_first': 'is_weekend',
            'vehicle_id_nunique': 'active_vehicles'
        }
        agg.rename(columns=rename_dict, inplace=True)
        
        # Calculate additional features
        agg['delay_per_train'] = agg['avg_delay'] / agg['train_count'].clip(lower=1)
        agg['delay_variability'] = agg['delay_std'] / agg['train_count'].clip(lower=1)
        agg['delay_std'] = agg['delay_std'].fillna(0)
        agg['delay_variability'] = agg['delay_variability'].fillna(0)
        agg['vehicles_per_train'] = agg['active_vehicles'] / agg['train_count'].clip(lower=1)
        
        # Create target variable for supervised training
        # Identify anomalies based on the 99th percentile for each line
        agg['is_anomaly'] = 0
        for route in agg['route_id'].unique():
            for part in agg['part_of_day'].unique():
                mask = (agg['route_id'] == route) & (agg['part_of_day'] == part)
                if mask.sum() > 10:  # Enough data for reliable threshold
                    th = agg.loc[mask, 'avg_delay'].quantile(0.99)
                    agg.loc[mask & (agg['avg_delay'] > th), 'is_anomaly'] = 1
    except Exception as e:
        logger.error(f"Error in feature aggregation: {e}")
        logger.error(traceback.format_exc())
        # Create a simpler aggregation as fallback
        agg = df.groupby(['route_id']).agg({
            'delay': ['mean', 'std', 'max', 'min', 'count']
        }).reset_index()
        agg.columns = ['route_id', 'avg_delay', 'delay_std', 'max_delay', 'min_delay', 'train_count']
        agg['is_anomaly'] = (agg['avg_delay'] > agg['avg_delay'].quantile(0.95)).astype(int)
        agg['hour'] = df['hour'].mean()
        agg['day_of_week'] = df['day_of_week'].mode()[0]
        agg['is_weekend'] = df['is_weekend'].mode()[0]
        agg['active_vehicles'] = 1
        agg['delay_per_train'] = agg['avg_delay']
        agg['delay_variability'] = 0
        
    # Fill missing values
    agg = agg.fillna(0)
    
    logger.info(f"Created {len(agg)} feature records")
    logger.info(f"Anomalies: {agg['is_anomaly'].sum()} / {len(agg)} ({agg['is_anomaly'].mean():.2%})")
    
    return agg

def train_model(features):
    """Train anomaly detection model with improved parameters."""
    logger.info("Training anomaly detection model...")
    
    # Select features for training
    feature_cols = [
        'avg_delay', 'max_delay', 'min_delay', 'delay_std',
        'train_count', 'delay_per_train', 'delay_variability',
        'hour', 'day_of_week', 'is_weekend', 'active_vehicles'
    ]
    
    # Filter features that don't exist in the DataFrame
    feature_cols = [col for col in feature_cols if col in features.columns]
    
    X = features[feature_cols].values
    y = features['is_anomaly'].values
    
    logger.info(f"Training with {X.shape[0]} samples, {X.shape[1]} features")
    
    try:
        # Create and train model
        scaler = StandardScaler()
        clf = IsolationForest(
            n_estimators=200,  # More trees for better performance
            max_samples='auto',
            contamination=0.05,  # 5% expected anomaly rate
            random_state=42,
            n_jobs=-1  # Use all cores
        )
        
        pipeline = Pipeline([
            ('scaler', scaler),
            ('clf', clf)
        ])
        
        pipeline.fit(X)
        
        # Evaluate
        preds = (pipeline.predict(X) == -1).astype(int)
        true_anom = y.sum()
        pred_anom = preds.sum()
        overlap = ((y == 1) & (preds == 1)).sum()
        
        logger.info(f"Model evaluation:")
        logger.info(f"True anomalies: {true_anom}")
        logger.info(f"Predicted anomalies: {pred_anom}")
        logger.info(f"Overlapping anomalies: {overlap}")
        
        if true_anom > 0 and pred_anom > 0:
            precision = overlap / pred_anom if pred_anom > 0 else 0
            recall = overlap / true_anom if true_anom > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            
            logger.info(f"Precision: {precision:.4f}")
            logger.info(f"Recall: {recall:.4f}")
            logger.info(f"F1 Score: {f1:.4f}")
        
        return pipeline, feature_cols
    except Exception as e:
        logger.error(f"Error training model: {e}")
        logger.error(traceback.format_exc())
        # Create a simpler model as fallback
        logger.warning("Creating simplified fallback model")
        scaler = StandardScaler()
        clf = IsolationForest(random_state=42)
        pipeline = Pipeline([('scaler', scaler), ('clf', clf)])
        pipeline.fit(X)
        return pipeline, feature_cols

def export_model(pipeline, feature_cols):
    """Export trained model with error handling and backup."""
    logger.info("Exporting model...")
    
    # Ensure model directory exists
    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Create backup of previous model if it exists
    if os.path.exists(MODEL_OUTPUT_PATH):
        backup_path = f"{MODEL_OUTPUT_PATH}.bak"
        try:
            logger.info(f"Creating backup of previous model: {backup_path}")
            with open(MODEL_OUTPUT_PATH, 'rb') as src, open(backup_path, 'wb') as dst:
                dst.write(src.read())
        except Exception as e:
            logger.warning(f"Failed to create backup: {e}")
    
    # Export model based on available format
    if ONNX_AVAILABLE and MODEL_OUTPUT_PATH.endswith('.onnx'):
        try:
            # Prepare for ONNX conversion
            n_features = len(feature_cols)
            initial_types = [('input', FloatTensorType([None, n_features]))]
            
            # Convert model to ONNX
            onx = convert_sklearn(
                pipeline,
                initial_types=initial_types,
                name="subway_anomaly_detection",
                target_opset=15  # Newer ONNX version
            )
            
            # Save ONNX model
            with open(MODEL_OUTPUT_PATH, "wb") as f:
                f.write(onx.SerializeToString())
            logger.info(f"ONNX model exported to {MODEL_OUTPUT_PATH}")
            
            # Also save pickle for compatibility
            pkl_path = MODEL_OUTPUT_PATH.replace('.onnx', '.pkl')
            with open(pkl_path, 'wb') as f:
                pickle.dump(pipeline, f)
            logger.info(f"Pickle model saved to {pkl_path} for compatibility")
        except Exception as e:
            logger.error(f"Error exporting ONNX: {e}")
            logger.error(traceback.format_exc())
            logger.warning("Falling back to pickle export...")
            pkl_path = MODEL_OUTPUT_PATH.replace('.onnx', '.pkl')
            with open(pkl_path, 'wb') as f:
                pickle.dump(pipeline, f)
            logger.info(f"Pickle model saved to {pkl_path}")
    else:
        # Save in pickle format
        pkl_path = MODEL_OUTPUT_PATH.replace('.onnx', '.pkl')
        with open(pkl_path, 'wb') as f:
            pickle.dump(pipeline, f)
        logger.info(f"Pickle model saved to {pkl_path}")
    
    # Save scaler separately
    scaler = pipeline.named_steps['scaler']
    with open(os.path.join(MODEL_DIR, "scaler.pkl"), 'wb') as f:
        pickle.dump(scaler, f)
    logger.info(f"Scaler exported to {os.path.join(MODEL_DIR, 'scaler.pkl')}")
    
    # Save feature information
    info = {
        'feature_columns': feature_cols, 
        'trained_at': datetime.now().isoformat(),
        'model_version': datetime.now().strftime('%Y%m%d_%H%M%S')
    }
    with open(os.path.join(MODEL_DIR, 'feature_info.json'), 'w') as f:
        json.dump(info, f, indent=2)
    logger.info(f"Feature information saved to {os.path.join(MODEL_DIR, 'feature_info.json')}")

def notify_ml_service():
    """Notify ML service to reload the model with retry mechanism."""
    # Setup session with retry
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["POST"]
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    
    try:
        logger.info(f"Notifying ML service at {ML_SERVICE_URL} to reload model...")
        response = session.post(f"{ML_SERVICE_URL}/reload-model", timeout=10)
        if response.status_code == 200:
            logger.info("ML service notification successful")
            logger.info(f"Response: {response.json()}")
            return True
        else:
            logger.warning(f"ML service notification failed: {response.status_code}")
            logger.warning(f"Response: {response.text}")
            return False
    except Exception as e:
        logger.error(f"Error notifying ML service: {e}")
        return False

def main():
    """Main training function with improved error handling."""
    start_time = datetime.now()
    logger.info("=== Starting NYC Subway Anomaly Detection Model Training ===")
    logger.info(f"Start time: {start_time.isoformat()}")
    logger.info("="*80)
    
    try:
        # Get historical data
        df = get_historical_data()
        
        # Extract features
        features = extract_features(df)
        
        # Check for sufficient data
        if len(features) < 100:
            logger.warning(f"Warning: only {len(features)} records for training. Results may be degraded.")
        
        # Train model
        pipeline, cols = train_model(features)
        
        # Export model
        export_model(pipeline, cols)
        
        # Notify ML service
        notify_ml_service()
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds() / 60
        logger.info("\nModel training completed successfully!")
        logger.info(f"End time: {end_time.isoformat()}")
        logger.info(f"Total duration: {duration:.2f} minutes")
        return 0
    except Exception as e:
        logger.error(f"Training process failed: {e}")
        logger.error(traceback.format_exc())
        return 1

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)