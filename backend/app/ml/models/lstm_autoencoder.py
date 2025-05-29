"""
LSTM Autoencoder for sequence anomaly detection.
Captures temporal dependencies in subway traffic patterns.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from app.config import get_settings

settings = get_settings()


class SubwaySequenceDataset(Dataset):
    """PyTorch dataset for subway time-series sequences."""
    
    def __init__(self, data: np.ndarray, sequence_length: int):
        self.data = data
        self.sequence_length = sequence_length
        
    def __len__(self):
        return len(self.data) - self.sequence_length + 1
    
    def __getitem__(self, idx):
        sequence = self.data[idx:idx + self.sequence_length]
        return torch.FloatTensor(sequence)


class LSTMAutoencoder(nn.Module):
    """LSTM-based autoencoder for anomaly detection."""
    
    def __init__(self, input_dim: int, hidden_dim: int = 128, num_layers: int = 2):
        super().__init__()
        
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        
        # Encoder
        self.encoder = nn.LSTM(
            input_size=input_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.2 if num_layers > 1 else 0,
        )
        
        # Bottleneck
        self.bottleneck = nn.Linear(hidden_dim, hidden_dim // 2)
        self.activation = nn.ReLU()
        self.expand = nn.Linear(hidden_dim // 2, hidden_dim)
        
        # Decoder
        self.decoder = nn.LSTM(
            input_size=hidden_dim,
            hidden_size=hidden_dim,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.2 if num_layers > 1 else 0,
        )
        
        self.output_layer = nn.Linear(hidden_dim, input_dim)
        
    def forward(self, x):
        # Encode
        encoded, (hidden, cell) = self.encoder(x)
        
        # Bottleneck (using last hidden state)
        bottleneck = self.bottleneck(hidden[-1])
        bottleneck = self.activation(bottleneck)
        expanded = self.expand(bottleneck)
        
        # Repeat for sequence length
        batch_size, seq_len, _ = x.shape
        expanded = expanded.unsqueeze(1).repeat(1, seq_len, 1)
        
        # Decode
        decoded, _ = self.decoder(expanded)
        output = self.output_layer(decoded)
        
        return output


class LSTMDetector:
    """LSTM Autoencoder anomaly detector."""
    
    def __init__(
        self,
        sequence_length: int = None,
        hidden_size: int = None,
        threshold_percentile: float = 95,
    ):
        self.sequence_length = sequence_length or settings.lstm_sequence_length
        self.hidden_size = hidden_size or settings.lstm_hidden_size
        self.threshold_percentile = threshold_percentile
        
        self.model = None
        self.feature_columns = []
        self.scaler_params = {}
        self.threshold = None
        self.version = None
        
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
    def prepare_sequences(self, df: pd.DataFrame) -> Tuple[np.ndarray, pd.DataFrame]:
        """Prepare sequential features for LSTM."""
        
        # Select features
        feature_cols = [
            "headway_seconds",
            "dwell_time_seconds",
            "delay_seconds",
            "hour",
            "is_rush_hour",
        ]
        
        self.feature_columns = [col for col in feature_cols if col in df.columns]
        
        # Fill missing values
        df_filled = df[self.feature_columns].fillna(0)
        
        # Normalize features
        normalized_data = []
        for col in self.feature_columns:
            values = df_filled[col].values
            mean = values.mean()
            std = values.std() + 1e-7  # Avoid division by zero
            
            self.scaler_params[col] = {"mean": mean, "std": std}
            normalized = (values - mean) / std
            normalized_data.append(normalized)
        
        # Stack features
        X = np.stack(normalized_data, axis=1)
        
        return X.T, df  # Return transposed for (samples, features)
    
    def train(self, train_data: pd.DataFrame, epochs: int = 50) -> Dict[str, float]:
        """Train LSTM autoencoder."""
        
        # Prepare data
        X, _ = self.prepare_sequences(train_data)
        
        # Create dataset and loader
        dataset = SubwaySequenceDataset(X, self.sequence_length)
        dataloader = DataLoader(dataset, batch_size=32, shuffle=True)
        
        # Initialize model
        input_dim = len(self.feature_columns)
        self.model = LSTMAutoencoder(input_dim, self.hidden_size).to(self.device)
        
        # Training setup
        criterion = nn.MSELoss()
        optimizer = torch.optim.Adam(self.model.parameters(), lr=0.001)
        
        # Training loop
        train_losses = []
        self.model.train()
        
        for epoch in range(epochs):
            epoch_losses = []
            
            for batch in dataloader:
                batch = batch.to(self.device)
                
                # Forward pass
                reconstructed = self.model(batch)
                loss = criterion(reconstructed, batch)
                
                # Backward pass
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                
                epoch_losses.append(loss.item())
            
            avg_loss = np.mean(epoch_losses)
            train_losses.append(avg_loss)
            
            if epoch % 10 == 0:
                print(f"Epoch {epoch}/{epochs}, Loss: {avg_loss:.4f}")
        
        # Calculate threshold on training data
        self.model.eval()
        reconstruction_errors = []
        
        with torch.no_grad():
            for batch in dataloader:
                batch = batch.to(self.device)
                reconstructed = self.model(batch)
                errors = torch.mean((batch - reconstructed) ** 2, dim=(1, 2))
                reconstruction_errors.extend(errors.cpu().numpy())
        
        self.threshold = np.percentile(reconstruction_errors, self.threshold_percentile)
        
        # Set version
        self.version = f"lstm_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        metrics = {
            "train_samples": len(X),
            "sequence_length": self.sequence_length,
            "final_loss": float(train_losses[-1]),
            "threshold": float(self.threshold),
            "input_dim": input_dim,
        }
        
        return metrics
    
    def predict(self, data: pd.DataFrame) -> List[Dict]:
        """Detect anomalies using reconstruction error."""
        
        if self.model is None:
            raise ValueError("Model not trained")
        
        # Prepare sequences
        X, original_df = self.prepare_sequences(data)
        
        # Skip if not enough data for sequences
        if len(X) < self.sequence_length:
            return []
        
        # Create dataset
        dataset = SubwaySequenceDataset(X, self.sequence_length)
        dataloader = DataLoader(dataset, batch_size=32, shuffle=False)
        
        # Calculate reconstruction errors
        self.model.eval()
        reconstruction_errors = []
        
        with torch.no_grad():
            for batch in dataloader:
                batch = batch.to(self.device)
                reconstructed = self.model(batch)
                errors = torch.mean((batch - reconstructed) ** 2, dim=2)  # (batch, seq_len)
                reconstruction_errors.append(errors.cpu().numpy())
        
        # Concatenate all errors
        if reconstruction_errors:
            all_errors = np.concatenate(reconstruction_errors, axis=0)
        else:
            return []
        
        # Detect anomalies
        anomalies = []
        
        for seq_idx in range(len(all_errors)):
            seq_errors = all_errors[seq_idx]
            
            # Check each position in sequence
            for pos_idx, error in enumerate(seq_errors):
                if error > self.threshold:
                    # Map back to original dataframe index
                    data_idx = seq_idx + pos_idx
                    
                    if data_idx < len(original_df):
                        row = original_df.iloc[data_idx]
                        
                        anomaly = {
                            "station_id": row.get("current_station"),
                            "line": row.get("line"),
                            "anomaly_type": "sequence",
                            "severity": float(min(1.0, error / (self.threshold * 2))),
                            "model_name": "lstm_autoencoder",
                            "model_version": self.version,
                            "features": {
                                col: float(row[col]) for col in self.feature_columns
                                if not pd.isna(row[col])
                            },
                            "metadata": {
                                "reconstruction_error": float(error),
                                "threshold": float(self.threshold),
                                "sequence_position": pos_idx,
                            }
                        }
                        
                        anomalies.append(anomaly)
        
        return anomalies
    
    def save(self, path: Path):
        """Save model artifacts."""
        path.mkdir(parents=True, exist_ok=True)
        
        # Save model state
        torch.save(self.model.state_dict(), path / "model.pth")
        
        # Save metadata
        metadata = {
            "version": self.version,
            "sequence_length": self.sequence_length,
            "hidden_size": self.hidden_size,
            "threshold": float(self.threshold) if self.threshold else None,
            "threshold_percentile": self.threshold_percentile,
            "feature_columns": self.feature_columns,
            "scaler_params": self.scaler_params,
            "input_dim": len(self.feature_columns),
            "trained_at": datetime.utcnow().isoformat(),
        }
        
        with open(path / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
    
    def load(self, path: Path):
        """Load model artifacts."""
        
        # Load metadata
        with open(path / "metadata.json", "r") as f:
            metadata = json.load(f)
            self.version = metadata["version"]
            self.sequence_length = metadata["sequence_length"]
            self.hidden_size = metadata["hidden_size"]
            self.threshold = metadata["threshold"]
            self.feature_columns = metadata["feature_columns"]
            self.scaler_params = metadata["scaler_params"]
            input_dim = metadata["input_dim"]
        
        # Initialize and load model
        self.model = LSTMAutoencoder(input_dim, self.hidden_size).to(self.device)
        self.model.load_state_dict(torch.load(path / "model.pth", map_location=self.device))
        self.model.eval()