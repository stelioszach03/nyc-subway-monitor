"""
Fixed model training with proper error handling and initialization.
"""

import asyncio
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import crud
from app.db.database import AsyncSessionLocal
from app.ml.features import FeatureExtractor
from app.ml.models.isolation_forest import IsolationForestDetector
from app.ml.models.lstm_autoencoder import LSTMDetector

logger = structlog.get_logger()
settings = get_settings()


class ModelTrainer:
    """Fixed ML model training orchestrator."""
    
    def __init__(self):
        self.models_dir = Path("/app/models/artifacts")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.feature_extractor = FeatureExtractor()
        self.active_models: Dict[str, any] = {}
        
    async def load_or_train_models(self):
        """Load existing models or train new ones with proper error handling."""
        async with AsyncSessionLocal() as db:
            # Check for existing models
            active_models = await crud.get_active_models(db)
            
            models_loaded = {
                "isolation_forest": False,
                "lstm_autoencoder": False,
            }
            
            # Try to load existing models
            for model_record in active_models:
                if model_record.artifact_path:
                    path = Path(model_record.artifact_path)
                    if path.exists():
                        try:
                            if model_record.model_type == "isolation_forest":
                                model = IsolationForestDetector()
                                model.load(path)
                                self.active_models["isolation_forest"] = model
                                models_loaded["isolation_forest"] = True
                                logger.info(f"Loaded isolation_forest model: {model_record.version}")
                                
                            elif model_record.model_type == "lstm_autoencoder":
                                model = LSTMDetector()
                                model.load(path)
                                self.active_models["lstm_autoencoder"] = model
                                models_loaded["lstm_autoencoder"] = True
                                logger.info(f"Loaded lstm_autoencoder model: {model_record.version}")
                                
                        except Exception as e:
                            logger.error(f"Failed to load {model_record.model_type}: {e}")
            
            # Check if we have enough data for training
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            
            positions = await crud.get_train_positions_for_training(
                db, start_time, end_time
            )
            
            logger.info(f"Found {len(positions)} training samples")
            
            # Always create at least placeholder models
            for model_type, loaded in models_loaded.items():
                if not loaded:
                    if len(positions) >= 100:
                        logger.info(f"Training new {model_type} model")
                        try:
                            await self.train_model(model_type, db)
                        except Exception as e:
                            logger.error(f"Failed to train {model_type}: {e}")
                            # Create placeholder model
                            if model_type == "isolation_forest":
                                self.active_models["isolation_forest"] = IsolationForestDetector()
                            elif model_type == "lstm_autoencoder":
                                self.active_models["lstm_autoencoder"] = LSTMDetector()
                    else:
                        logger.warning(f"Not enough data to train {model_type}, creating placeholder")
                        if model_type == "isolation_forest":
                            self.active_models["isolation_forest"] = IsolationForestDetector()
                        elif model_type == "lstm_autoencoder":
                            self.active_models["lstm_autoencoder"] = LSTMDetector()
    
    async def train_model(self, model_type: str, db: AsyncSession) -> Optional[Dict]:
        """Train a specific model type with error handling."""
        
        # Get training data
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=7)
        
        positions = await crud.get_train_positions_for_training(
            db, start_time, end_time
        )
        
        if len(positions) < 100:
            logger.warning(f"Insufficient data for {model_type}: {len(positions)} samples")
            return None
        
        # Convert to DataFrame
        data = []
        for p in positions:
            data.append({
                "timestamp": p.timestamp,
                "trip_id": p.trip_id,
                "route_id": p.route_id,
                "line": p.line,
                "current_station": p.current_station,
                "headway_seconds": p.headway_seconds or 0,
                "dwell_time_seconds": p.dwell_time_seconds or 0,
                "delay_seconds": p.delay_seconds,
                "direction": p.direction,
            })
        
        df = pd.DataFrame(data)
        
        # Add temporal features
        df['hour'] = df['timestamp'].dt.hour
        df['day_of_week'] = df['timestamp'].dt.dayofweek
        df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)
        df['is_rush_hour'] = df['timestamp'].apply(
            lambda x: (7 <= x.hour <= 10 or 17 <= x.hour <= 20) and x.weekday() < 5
        ).astype(int)
        
        # Get git SHA
        git_sha = self._get_git_sha()
        
        # Train model
        try:
            if model_type == "isolation_forest":
                model = IsolationForestDetector()
                metrics = model.train(df)
                
            elif model_type == "lstm_autoencoder":
                model = LSTMDetector()
                metrics = model.train(df, epochs=30)
                
            else:
                raise ValueError(f"Unknown model type: {model_type}")
            
            # Save model
            model_path = self.models_dir / model.version
            model.save(model_path)
            
            # Update database
            await crud.create_model_artifact(
                db,
                model_type=model_type,
                version=model.version,
                git_sha=git_sha,
                metrics=metrics,
                artifact_path=str(model_path),
                training_samples=len(df),
            )
            
            # Set as active
            await crud.set_active_model(db, model_type, model.version)
            await db.commit()
            
            # Update in-memory reference
            self.active_models[model_type] = model
            
            logger.info(f"Trained {model_type} model", version=model.version, metrics=metrics)
            
            return metrics
            
        except Exception as e:
            logger.error(f"Training failed for {model_type}: {e}")
            raise
    
    def _get_git_sha(self) -> Optional[str]:
        """Get current git commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()[:8]
        except Exception:
            return None
    
    def get_active_model(self, model_type: str):
        """Get active model instance."""
        return self.active_models.get(model_type)
