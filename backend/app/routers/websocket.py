"""
Fixed WebSocket implementation with proper connection management.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from uuid import uuid4

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.database import AsyncSessionLocal
from app.schemas.anomaly import WebSocketMessage

logger = structlog.get_logger()
settings = get_settings()
router = APIRouter()


class ConnectionManager:
    """WebSocket connection manager with reconnection support."""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.subscriptions: Dict[str, Dict] = {}
        self.heartbeat_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, client_id: str = None) -> str:
        """Accept new WebSocket connection."""
        if not client_id:
            client_id = f"client_{uuid4().hex[:8]}"
        
        try:
            await websocket.accept()
            async with self._lock:
                self.active_connections[client_id] = websocket
                self.subscriptions[client_id] = {}
            
            logger.info(f"WebSocket connected: {client_id}")
            
            # Start heartbeat if not running
            if not self.heartbeat_task or self.heartbeat_task.done():
                self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            
            return client_id
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            raise
    
    async def disconnect(self, client_id: str):
        """Remove disconnected client."""
        async with self._lock:
            self.active_connections.pop(client_id, None)
            self.subscriptions.pop(client_id, None)
        logger.info(f"WebSocket disconnected: {client_id}")
    
    async def send_personal_message(self, message: dict, client_id: str) -> bool:
        """Send message to specific client."""
        websocket = self.active_connections.get(client_id)
        if websocket:
            try:
                await websocket.send_json(message)
                return True
            except Exception as e:
                logger.error(f"Error sending to {client_id}: {e}")
                await self.disconnect(client_id)
        return False
    
    async def broadcast(self, message: dict, filters: Optional[Dict] = None):
        """Broadcast message to all matching subscribers."""
        disconnected = []
        
        # Create tasks for concurrent sending
        tasks = []
        for client_id, websocket in list(self.active_connections.items()):
            if filters and not self._matches_subscription(client_id, filters):
                continue
            
            tasks.append(self._send_with_error_handling(websocket, message, client_id))
        
        # Execute all sends concurrently
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Clean up failed connections
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    client_id = list(self.active_connections.keys())[i]
                    disconnected.append(client_id)
        
        # Remove disconnected clients
        for client_id in disconnected:
            await self.disconnect(client_id)
    
    async def _send_with_error_handling(self, websocket: WebSocket, message: dict, client_id: str):
        """Send message with error handling."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Broadcast error for {client_id}: {e}")
            raise
    
    def update_subscription(self, client_id: str, filters: Dict):
        """Update client's subscription filters."""
        if client_id in self.subscriptions:
            self.subscriptions[client_id] = filters
            logger.info(f"Updated subscription for {client_id}: {filters}")
    
    def _matches_subscription(self, client_id: str, message_filters: Dict) -> bool:
        """Check if message matches client's subscription."""
        client_filters = self.subscriptions.get(client_id, {})
        
        if not client_filters:
            return True
        
        for key, value in client_filters.items():
            if key in message_filters and message_filters[key] != value:
                return False
        
        return True
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats to detect stale connections."""
        while self.active_connections:
            try:
                message = {
                    "type": "heartbeat",
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": {"active_connections": len(self.active_connections)}
                }
                
                await self.broadcast(message)
                await asyncio.sleep(settings.ws_heartbeat_interval)
                
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(5)


# Global connection manager
manager = ConnectionManager()


@router.websocket("/anomalies")
async def websocket_anomalies(websocket: WebSocket):
    """WebSocket endpoint for real-time anomaly updates."""
    client_id = None
    
    try:
        # Accept connection
        client_id = await manager.connect(websocket)
        
        # Send initial connection message
        await manager.send_personal_message(
            {
                "type": "connected",
                "client_id": client_id,
                "timestamp": datetime.utcnow().isoformat()
            },
            client_id
        )
        
        # Message handling loop
        while True:
            try:
                # Receive with timeout to allow periodic checks
                raw_data = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=60.0
                )
                
                # Parse message
                try:
                    data = json.loads(raw_data)
                except json.JSONDecodeError:
                    await manager.send_personal_message(
                        {"type": "error", "message": "Invalid JSON"},
                        client_id
                    )
                    continue
                
                # Handle message types
                if data.get("type") == "subscribe":
                    filters = data.get("filters", {})
                    manager.update_subscription(client_id, filters)
                    
                    await manager.send_personal_message(
                        {
                            "type": "subscribed",
                            "filters": filters,
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        client_id
                    )
                
                elif data.get("type") == "ping":
                    await manager.send_personal_message(
                        {
                            "type": "pong",
                            "timestamp": datetime.utcnow().isoformat()
                        },
                        client_id
                    )
                
                elif data.get("type") == "unsubscribe":
                    manager.update_subscription(client_id, {})
                    await manager.send_personal_message(
                        {"type": "unsubscribed"},
                        client_id
                    )
                    
            except asyncio.TimeoutError:
                # Send keepalive ping
                if not await manager.send_personal_message(
                    {"type": "ping"},
                    client_id
                ):
                    break
                    
    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected normally")
    except Exception as e:
        logger.error(f"WebSocket error for {client_id}: {e}")
    finally:
        if client_id:
            await manager.disconnect(client_id)


async def broadcast_anomaly(anomaly_data: Dict):
    """Broadcast new anomaly to subscribers."""
    message = {
        "type": "anomaly",
        "data": anomaly_data,
        "timestamp": datetime.utcnow().isoformat()
    }
    
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
        "clients": list(manager.active_connections.keys()),
        "subscriptions": dict(manager.subscriptions),
        "timestamp": datetime.utcnow().isoformat()
    }
