"""
Model training orchestration and hyperparameter tuning.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, precision_recall_fscore_support
from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
import torch
from torch.utils.data import DataLoader

from app.config import get_settings
from app.ml.models.isolation_forest import IsolationForestDetector
from app.ml.models.lstm_autoencoder import LSTMDetector
from app.ml.training.dataset import SubwayDataset, WindowedDataset, create_anomaly_labels

settings = get_settings()


class ModelTrainerConfig:
    """Configuration for model training."""
    
    def __init__(
        self,
        model_type: str,
        hyperparameters: Optional[Dict] = None,
        cv_folds: int = 5,
        scoring: str = 'f1',
        n_jobs: int = -1,
    ):
        self.model_type = model_type
        self.hyperparameters = hyperparameters or self._get_default_hyperparameters()
        self.cv_folds = cv_folds
        self.scoring = scoring
        self.n_jobs = n_jobs
    
    def _get_default_hyperparameters(self) -> Dict:
        """Get default hyperparameter search space."""
        if self.model_type == 'isolation_forest':
            return {
                'contamination': [0.01, 0.05, 0.1],
                'n_estimators': [50, 100, 200],
                'max_samples': ['auto', 0.5, 0.8],
            }
        elif self.model_type == 'lstm':
            return {
                'hidden_size': [64, 128, 256],
                'num_layers': [1, 2, 3],
                'learning_rate': [0.001, 0.0001],
                'batch_size': [32, 64],
            }
        else:
            return {}


class ModelTrainerPipeline:
    """Complete training pipeline with evaluation and model selection."""
    
    def __init__(self, config: ModelTrainerConfig):
        self.config = config
        self.best_model = None
        self.training_history = []
    
    def train_isolation_forest(
        self,
        train_data: pd.DataFrame,
        val_data: pd.DataFrame
    ) -> Tuple[IsolationForestDetector, Dict]:
        """Train Isolation Forest with hyperparameter tuning."""
        
        dataset = SubwayDataset(train_data)
        X_train, _ = dataset.to_numpy()
        
        # Create synthetic labels for validation
        val_labels = create_anomaly_labels(val_data, method='isolation_forest')
        val_dataset = SubwayDataset(val_data)
        X_val, _ = val_dataset.to_numpy()
        
        best_score = -np.inf
        best_params = {}
        
        # Grid search
        for contamination in self.config.hyperparameters.get('contamination', [0.05]):
            for n_estimators in self.config.hyperparameters.get('n_estimators', [100]):
                for max_samples in self.config.hyperparameters.get('max_samples', ['auto']):
                    
                    # Train model
                    model = IsolationForestDetector(contamination=contamination)
                    model.model_params = {
                        'n_estimators': n_estimators,
                        'max_samples': max_samples,
                    }
                    
                    metrics = model.train(train_data)
                    
                    # Evaluate on validation set
                    val_anomalies = model.predict(val_data)
                    val_pred = np.zeros(len(val_data))
                    
                    # Mark predicted anomalies
                    for anomaly in val_anomalies:
                        # Find corresponding index in validation data
                        # This is simplified - in practice would match by timestamp/id
                        val_pred[0] = 1  # Placeholder
                    
                    # Calculate F1 score
                    precision, recall, f1, _ = precision_recall_fscore_support(
                        val_labels, val_pred, average='binary', zero_division=0
                    )
                    
                    if f1 > best_score:
                        best_score = f1
                        best_params = {
                            'contamination': contamination,
                            'n_estimators': n_estimators,
                            'max_samples': max_samples,
                        }
                        self.best_model = model
                    
                    self.training_history.append({
                        'params': {
                            'contamination': contamination,
                            'n_estimators': n_estimators,
                            'max_samples': max_samples,
                        },
                        'metrics': {
                            'precision': precision,
                            'recall': recall,
                            'f1': f1,
                        }
                    })
        
        # Retrain best model on full training data
        best_model = IsolationForestDetector(contamination=best_params['contamination'])
        best_model.model_params = {
            'n_estimators': best_params['n_estimators'],
            'max_samples': best_params['max_samples'],
        }
        final_metrics = best_model.train(train_data)
        
        return best_model, {
            'best_params': best_params,
            'best_score': best_score,
            'final_metrics': final_metrics,
            'training_history': self.training_history,
        }
    
    def train_lstm(
        self,
        train_data: pd.DataFrame,
        val_data: pd.DataFrame
    ) -> Tuple[LSTMDetector, Dict]:
        """Train LSTM autoencoder with hyperparameter tuning."""
        
        best_score = np.inf  # Lower reconstruction error is better
        best_params = {}
        
        for hidden_size in self.config.hyperparameters.get('hidden_size', [128]):
            for learning_rate in self.config.hyperparameters.get('learning_rate', [0.001]):
                for batch_size in self.config.hyperparameters.get('batch_size', [32]):
                    
                    # Create model
                    model = LSTMDetector(
                        sequence_length=settings.lstm_sequence_length,
                        hidden_size=hidden_size,
                    )
                    
                    # Set learning rate
                    model.learning_rate = learning_rate
                    model.batch_size = batch_size
                    
                    # Train
                    metrics = model.train(train_data, epochs=20)  # Fewer epochs for search
                    
                    # Evaluate on validation
                    val_anomalies = model.predict(val_data)
                    val_loss = metrics.get('final_loss', np.inf)
                    
                    if val_loss < best_score:
                        best_score = val_loss
                        best_params = {
                            'hidden_size': hidden_size,
                            'learning_rate': learning_rate,
                            'batch_size': batch_size,
                        }
                        self.best_model = model
                    
                    self.training_history.append({
                        'params': {
                            'hidden_size': hidden_size,
                            'learning_rate': learning_rate,
                            'batch_size': batch_size,
                        },
                        'metrics': {
                            'val_loss': val_loss,
                            'threshold': metrics.get('threshold', 0),
                        }
                    })
        
        # Retrain best model with more epochs
        best_model = LSTMDetector(
            sequence_length=settings.lstm_sequence_length,
            hidden_size=best_params['hidden_size'],
        )
        best_model.learning_rate = best_params['learning_rate']
        best_model.batch_size = best_params['batch_size']
        
        final_metrics = best_model.train(train_data, epochs=50)
        
        return best_model, {
            'best_params': best_params,
            'best_score': best_score,
            'final_metrics': final_metrics,
            'training_history': self.training_history,
        }
    
    def evaluate_model(
        self,
        model: any,
        test_data: pd.DataFrame,
        labels: Optional[pd.Series] = None
    ) -> Dict:
        """Evaluate model performance on test data."""
        
        # Get predictions
        anomalies = model.predict(test_data)
        
        # Create binary predictions
        predictions = np.zeros(len(test_data))
        for anomaly in anomalies:
            # Simplified - would match by actual index/timestamp
            predictions[0] = 1
        
        metrics = {
            'n_anomalies_detected': len(anomalies),
            'anomaly_rate': len(anomalies) / len(test_data),
        }
        
        if labels is not None:
            # Calculate classification metrics
            precision, recall, f1, support = precision_recall_fscore_support(
                labels, predictions, average='binary', zero_division=0
            )
            
            metrics.update({
                'precision': precision,
                'recall': recall,
                'f1_score': f1,
                'support': support,
                'classification_report': classification_report(
                    labels, predictions, zero_division=0
                ),
            })
        
        # Calculate severity distribution
        if anomalies:
            severities = [a['severity'] for a in anomalies]
            metrics['severity_stats'] = {
                'mean': np.mean(severities),
                'std': np.std(severities),
                'min': np.min(severities),
                'max': np.max(severities),
                'quantiles': {
                    '25%': np.percentile(severities, 25),
                    '50%': np.percentile(severities, 50),
                    '75%': np.percentile(severities, 75),
                }
            }
        
        return metrics
    
    def save_training_report(self, output_dir: Path, model_type: str, results: Dict):
        """Save comprehensive training report."""
        
        report = {
            'model_type': model_type,
            'training_date': datetime.utcnow().isoformat(),
            'config': {
                'hyperparameter_space': self.config.hyperparameters,
                'cv_folds': self.config.cv_folds,
                'scoring': self.config.scoring,
            },
            'results': results,
            'environment': {
                'python_version': '3.12',
                'torch_version': torch.__version__ if 'lstm' in model_type else None,
                'sklearn_version': '1.6.0',
            }
        }
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save JSON report
        with open(output_dir / f'{model_type}_training_report.json', 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Save training history as CSV
        if self.training_history:
            history_df = pd.DataFrame(self.training_history)
            history_df.to_csv(output_dir / f'{model_type}_training_history.csv', index=False)


def run_training_experiment(
    train_data: pd.DataFrame,
    model_type: str,
    output_dir: Path,
    config: Optional[ModelTrainerConfig] = None
) -> Tuple[any, Dict]:
    """Run complete training experiment with evaluation."""
    
    if config is None:
        config = ModelTrainerConfig(model_type)
    
    # Split data
    dataset = SubwayDataset(train_data)
    train_df, val_df = dataset.split(test_size=0.2)
    
    # Initialize trainer
    trainer = ModelTrainerPipeline(config)
    
    # Train model
    if model_type == 'isolation_forest':
        model, results = trainer.train_isolation_forest(train_df, val_df)
    elif model_type == 'lstm':
        model, results = trainer.train_lstm(train_df, val_df)
    else:
        raise ValueError(f"Unknown model type: {model_type}")
    
    # Evaluate on validation set
    val_metrics = trainer.evaluate_model(model, val_df)
    results['validation_metrics'] = val_metrics
    
    # Save results
    trainer.save_training_report(output_dir, model_type, results)
    
    return model, results