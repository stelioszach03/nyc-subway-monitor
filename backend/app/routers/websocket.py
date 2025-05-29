"""
WebSocket endpoints for real-time anomaly streaming.
Supports filtered subscriptions and connection management.
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional, Set

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import AsyncSessionLocal
from app.schemas.anomaly import WebSocketMessage

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


class ConnectionManager:
    """Manages WebSocket connections and subscriptions."""
    
    def __init__(self):
        # Map of client_id -> WebSocket
        self.active_connections: Dict[str, WebSocket] = {}
        # Map of client_id -> subscription filters
        self.subscriptions: Dict[str, Dict] = {}
        # Background task for heartbeats
        self.heartbeat_task: Optional[asyncio.Task] = None
    
    async def connect(self, websocket: WebSocket, client_id: str):
        """Accept new WebSocket connection."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.subscriptions[client_id] = {}
        logger.info(f"WebSocket connected: {client_id}")
        
        # Start heartbeat if not running
        if not self.heartbeat_task or self.heartbeat_task.done():
            self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
    
    def disconnect(self, client_id: str):
        """Remove disconnected client."""
        self.active_connections.pop(client_id, None)
        self.subscriptions.pop(client_id, None)
        logger.info(f"WebSocket disconnected: {client_id}")
    
    async def send_personal_message(self, message: str, client_id: str):
        """Send message to specific client."""
        websocket = self.active_connections.get(client_id)
        if websocket:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to {client_id}: {e}")
                self.disconnect(client_id)
    
    async def broadcast(self, message: str, filters: Optional[Dict] = None):
        """Broadcast message to all matching subscribers."""
        disconnected = []
        
        for client_id, websocket in self.active_connections.items():
            # Check if client subscribed to this type of message
            if filters and not self._matches_subscription(client_id, filters):
                continue
            
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting to {client_id}: {e}")
                disconnected.append(client_id)
        
        # Clean up disconnected clients
        for client_id in disconnected:
            self.disconnect(client_id)
    
    def update_subscription(self, client_id: str, filters: Dict):
        """Update client's subscription filters."""
        if client_id in self.subscriptions:
            self.subscriptions[client_id] = filters
            logger.info(f"Updated subscription for {client_id}: {filters}")
    
    def _matches_subscription(self, client_id: str, message_filters: Dict) -> bool:
        """Check if message matches client's subscription."""
        client_filters = self.subscriptions.get(client_id, {})
        
        # If no filters set, receive all messages
        if not client_filters:
            return True
        
        # Check each filter
        for key, value in client_filters.items():
            if key in message_filters and message_filters[key] != value:
                return False
        
        return True
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to detect stale connections."""
        while self.active_connections:
            message = WebSocketMessage(
                type="heartbeat",
                timestamp=datetime.utcnow(),
                data={"active_connections": len(self.active_connections)}
            ).json()
            
            await self.broadcast(message)
            await asyncio.sleep(settings.ws_heartbeat_interval)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/anomalies")
async def websocket_anomalies(websocket: WebSocket):
    """WebSocket endpoint for real-time anomaly updates."""
    import uuid
    client_id = str(uuid.uuid4())
    
    await manager.connect(websocket, client_id)
    
    try:
        # Send initial connection message
        await manager.send_personal_message(
            WebSocketMessage(
                type="connected",
                data={"client_id": client_id}
            ).json(),
            client_id
        )
        
        while True:
            # Receive messages from client
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Handle different message types
            if message["type"] == "subscribe":
                # Update subscription filters
                filters = message.get("filters", {})
                manager.update_subscription(client_id, filters)
                
                await manager.send_personal_message(
                    WebSocketMessage(
                        type="subscribed",
                        data={"filters": filters}
                    ).json(),
                    client_id
                )
            
            elif message["type"] == "ping":
                # Respond to ping
                await manager.send_personal_message(
                    WebSocketMessage(type="pong").json(),
                    client_id
                )
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
        manager.disconnect(client_id)


async def broadcast_anomaly(anomaly_data: Dict):
    """Helper to broadcast new anomaly to subscribers."""
    message = WebSocketMessage(
        type="anomaly",
        data=anomaly_data
    ).json()
    
    # Include filters for subscription matching
    filters = {
        "line": anomaly_data.get("line"),
        "station_id": anomaly_data.get("station_id"),
        "anomaly_type": anomaly_data.get("anomaly_type"),
    }
    
    await manager.broadcast(message, filters)


@router.get("/connections")
async def get_connections():
    """Get current WebSocket connection stats."""
    return {
        "active_connections": len(manager.active_connections),
        "subscriptions": {
            client_id: filters
            for client_id, filters in manager.subscriptions.items()
        }
    }