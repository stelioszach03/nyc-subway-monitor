# --- backend/app/ml/train.py ---
"""
Model training orchestrator.
Handles periodic retraining and model versioning.
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
    """Orchestrates ML model training and deployment."""
    
    def __init__(self):
        self.models_dir = Path("models/artifacts")
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.feature_extractor = FeatureExtractor()
        self.active_models: Dict[str, any] = {}
        
    async def load_or_train_models(self):
        """Load existing models or create placeholders if no data exists."""
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
                                
                            elif model_record.model_type == "lstm_autoencoder":
                                model = LSTMDetector()
                                model.load(path)
                                self.active_models["lstm_autoencoder"] = model
                                models_loaded["lstm_autoencoder"] = True
                                
                            logger.info(f"Loaded {model_record.model_type} model", 
                                      version=model_record.version)
                        except Exception as e:
                            logger.error(f"Failed to load model {model_record.model_type}", 
                                       error=str(e))
            
            # Check if we have data to train with
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=7)
            
            positions = await crud.get_train_positions_for_training(
                db, start_time, end_time
            )
            
            if len(positions) < 100:
                logger.warning("Not enough data to train models", samples=len(positions))
                # Create placeholder models
                for model_type, loaded in models_loaded.items():
                    if not loaded:
                        logger.info(f"Creating placeholder {model_type} model")
                        if model_type == "isolation_forest":
                            self.active_models["isolation_forest"] = IsolationForestDetector()
                        elif model_type == "lstm_autoencoder":
                            self.active_models["lstm_autoencoder"] = LSTMDetector()
            else:
                # Train missing models
                for model_type, loaded in models_loaded.items():
                    if not loaded:
                        logger.info(f"Training new {model_type} model")
                        await self.train_model(model_type, db)
    
    async def train_model(self, model_type: str, db: AsyncSession) -> Optional[Dict]:
        """Train a specific model type."""
        
        # Get training data (last 7 days)
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=7)
        
        positions = await crud.get_train_positions_for_training(
            db, start_time, end_time
        )
        
        if len(positions) < 1000:
            logger.warning(f"Not enough data to train {model_type}", 
                         samples=len(positions))
            return None
        
        # Convert to DataFrame
        df = pd.DataFrame([
            {
                "trip_id": p.trip_id,
                "route_id": p.route_id,
                "line": p.line,
                "current_station": p.current_station,
                "timestamp": p.timestamp,
                "headway_seconds": p.headway_seconds,
                "dwell_time_seconds": p.dwell_time_seconds,
                "delay_seconds": p.delay_seconds,
                "direction": p.direction,
            }
            for p in positions
        ])
        
        # Add temporal features
        for idx, row in df.iterrows():
            temporal = self.feature_extractor.create_temporal_features(row["timestamp"])
            for key, value in temporal.items():
                df.loc[idx, key] = value
        
        # Compute rolling features
        df = self.feature_extractor.compute_rolling_features(df)
        
        # Get git SHA for versioning
        git_sha = self._get_git_sha()
        
        # Train model
        if model_type == "isolation_forest":
            model = IsolationForestDetector()
            metrics = model.train(df)
            
        elif model_type == "lstm_autoencoder":
            model = LSTMDetector()
            metrics = model.train(df, epochs=30)  # Fewer epochs for speed
            
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
        
        # Update in-memory reference
        self.active_models[model_type] = model
        
        logger.info(f"Trained {model_type} model", 
                   version=model.version, 
                   metrics=metrics)
        
        return metrics
    
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
    
    async def retrain_all_models(self):
        """Retrain all models with latest data."""
        async with AsyncSessionLocal() as db:
            results = {}
            
            for model_type in ["isolation_forest", "lstm_autoencoder"]:
                try:
                    metrics = await self.train_model(model_type, db)
                    results[model_type] = {"status": "success", "metrics": metrics}
                except Exception as e:
                    logger.error(f"Failed to train {model_type}", error=str(e))
                    results[model_type] = {"status": "failed", "error": str(e)}
            
            return results
    
    def get_active_model(self, model_type: str):
        """Get active model instance."""
        return self.active_models.get(model_type)


async def scheduled_retraining():
    """Background task for scheduled model retraining."""
    trainer = ModelTrainer()
    
    while True:
        # Wait until scheduled hour
        now = datetime.utcnow()
        target_hour = settings.model_retrain_hour
        
        # Calculate next training time
        next_train = now.replace(hour=target_hour, minute=0, second=0, microsecond=0)
        if now >= next_train:
            next_train += timedelta(days=1)
        
        wait_seconds = (next_train - now).total_seconds()
        logger.info(f"Next model training at {next_train}, waiting {wait_seconds}s")
        
        await asyncio.sleep(wait_seconds)
        
        # Run retraining
        logger.info("Starting scheduled model retraining")
        results = await trainer.retrain_all_models()
        logger.info("Model retraining complete", results=results)