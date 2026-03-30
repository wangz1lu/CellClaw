"""
WebSocket Manager - Real-time Task Updates
========================================

Provides WebSocket-based real-time updates for:
- Task status changes
- Job progress
- Notifications
- Dashboard sync
"""

import os
import asyncio
import json
import logging
from typing import Optional, Callable, Dict, Set
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class EventType(Enum):
    """WebSocket event types"""
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    JOB_STATUS_UPDATE = "job_status_update"
    NOTIFICATION = "notification"
    HEARTBEAT = "heartbeat"


@dataclass
class WSMessage:
    """WebSocket message structure"""
    event: str
    data: dict
    timestamp: str = None
    correlation_id: str = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()
    
    def to_json(self) -> str:
        return json.dumps({
            "event": self.event,
            "data": self.data,
            "timestamp": self.timestamp,
            "correlation_id": self.correlation_id
        })
    
    @classmethod
    def from_json(cls, raw: str) -> "WSMessage":
        obj = json.loads(raw)
        return cls(**obj)


class ConnectionManager:
    """
    Manages WebSocket connections per user/channel.
    """
    
    def __init__(self):
        # user_id -> set of websocket connections
        self._connections: Dict[str, Set] = {}
        # channel_id -> set of websocket connections  
        self._channel_connections: Dict[str, Set] = {}
        # connection -> metadata
        self._metadata: Dict = {}
    
    async def connect(self, websocket, user_id: str = None, channel_id: str = None):
        """Register a new WebSocket connection"""
        if user_id:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
        
        if channel_id:
            if channel_id not in self._channel_connections:
                self._channel_connections[channel_id] = set()
            self._channel_connections[channel_id].add(websocket)
        
        self._metadata[websocket] = {"user_id": user_id, "channel_id": channel_id}
        logger.info(f"WS connected: user={user_id}, channel={channel_id}")
    
    async def disconnect(self, websocket):
        """Unregister a WebSocket connection"""
        meta = self._metadata.pop(websocket, {})
        user_id = meta.get("user_id")
        channel_id = meta.get("channel_id")
        
        if user_id and websocket in self._connections.get(user_id, set()):
            self._connections[user_id].discard(websocket)
        
        if channel_id and websocket in self._channel_connections.get(channel_id, set()):
            self._channel_connections[channel_id].discard(websocket)
        
        logger.info(f"WS disconnected: user={user_id}, channel={channel_id}")
    
    async def send_to_user(self, user_id: str, message: WSMessage):
        """Send message to all connections for a user"""
        connections = self._connections.get(user_id, set())
        await self._broadcast(connections, message)
    
    async def send_to_channel(self, channel_id: str, message: WSMessage):
        """Send message to all connections in a channel"""
        connections = self._channel_connections.get(channel_id, set())
        await self._broadcast(connections, message)
    
    async def broadcast(self, message: WSMessage):
        """Broadcast to all connected clients"""
        all_connections = set()
        for conn_set in self._connections.values():
            all_connections.update(conn_set)
        for conn_set in self._channel_connections.values():
            all_connections.update(conn_set)
        await self._broadcast(all_connections, message)
    
    async def _broadcast(self, connections: Set, message: WSMessage):
        """Send to multiple connections, removing dead ones"""
        dead = set()
        for ws in connections:
            try:
                await ws.send_text(message.to_json())
            except Exception as e:
                logger.warning(f"WS send failed: {e}")
                dead.add(ws)
        
        # Cleanup dead connections
        for ws in dead:
            await self.disconnect(ws)


class WebSocketManager:
    """
    Main WebSocket manager for real-time updates.
    
    Usage:
        ws_manager = WebSocketManager()
        
        # In WebSocket endpoint:
        await ws_manager.handle_connect(websocket, user_id="123", channel_id="456")
        
        # When task updates:
        await ws_manager.emit_task_progress(task_id="abc", progress=0.5)
        await ws_manager.emit_task_completed(task_id="abc", result={...})
    """
    
    def __init__(self):
        self.connections = ConnectionManager()
        self._tasks: Dict[str, dict] = {}  # task_id -> task info
        self._handlers: Dict[EventType, list] = {e: [] for e in EventType}
    
    async def handle_connect(self, websocket, user_id: str = None, channel_id: str = None):
        """Handle new WebSocket connection"""
        await self.connections.connect(websocket, user_id, channel_id)
        
        # Send welcome message
        await websocket.send_text(WSMessage(
            event="connected",
            data={"user_id": user_id, "channel_id": channel_id}
        ).to_json())
    
    async def handle_disconnect(self, websocket):
        """Handle WebSocket disconnection"""
        await self.connections.disconnect(websocket)
    
    async def handle_message(self, websocket, raw_message: str):
        """Handle incoming WebSocket message from client"""
        try:
            msg = WSMessage.from_json(raw_message)
            
            # Handle different message types
            if msg.event == "ping":
                await websocket.send_text(WSMessage(
                    event="pong",
                    data={"timestamp": msg.timestamp}
                ).to_json())
            
            elif msg.event == "subscribe":
                # Client subscribing to task updates
                task_id = msg.data.get("task_id")
                if task_id:
                    # Add to subscriptions
                    pass
            
            elif msg.event == "unsubscribe":
                task_id = msg.data.get("task_id")
                if task_id:
                    # Remove from subscriptions
                    pass
            
        except Exception as e:
            logger.error(f"WS message handling error: {e}")
    
    # ─────────────────────────────────────────────────────────────────
    # Emit Events
    # ─────────────────────────────────────────────────────────────────
    
    async def emit_task_created(self, task_id: str, user_id: str, channel_id: str,
                               description: str, plan_id: str = None):
        """Emit task created event"""
        task_info = {
            "task_id": task_id,
            "user_id": user_id,
            "channel_id": channel_id,
            "description": description,
            "status": "created",
            "progress": 0.0,
            "created_at": datetime.now().isoformat()
        }
        self._tasks[task_id] = task_info
        
        msg = WSMessage(
            event=EventType.TASK_CREATED.value,
            data=task_info,
            correlation_id=plan_id
        )
        
        await self.connections.send_to_user(user_id, msg)
        if channel_id:
            await self.connections.send_to_channel(channel_id, msg)
    
    async def emit_task_progress(self, task_id: str, progress: float,
                                status: str = None, step: str = None):
        """Emit task progress update"""
        if task_id not in self._tasks:
            logger.warning(f"Task {task_id} not found for progress update")
            return
        
        task = self._tasks[task_id]
        task["progress"] = progress
        if status:
            task["status"] = status
        if step:
            task["current_step"] = step
        task["updated_at"] = datetime.now().isoformat()
        
        msg = WSMessage(
            event=EventType.TASK_PROGRESS.value,
            data={
                "task_id": task_id,
                "progress": progress,
                "status": task["status"],
                "step": step
            }
        )
        
        await self.connections.send_to_user(task["user_id"], msg)
    
    async def emit_task_completed(self, task_id: str, result: dict):
        """Emit task completed event"""
        if task_id not in self._tasks:
            logger.warning(f"Task {task_id} not found for completion")
            return
        
        task = self._tasks[task_id]
        task["status"] = "completed"
        task["progress"] = 1.0
        task["completed_at"] = datetime.now().isoformat()
        task["result"] = result
        
        msg = WSMessage(
            event=EventType.TASK_COMPLETED.value,
            data={
                "task_id": task_id,
                "result": result,
                "completed_at": task["completed_at"]
            }
        )
        
        await self.connections.send_to_user(task["user_id"], msg)
        if task.get("channel_id"):
            await self.connections.send_to_channel(task["channel_id"], msg)
    
    async def emit_task_failed(self, task_id: str, error: str):
        """Emit task failed event"""
        if task_id not in self._tasks:
            logger.warning(f"Task {task_id} not found for failure")
            return
        
        task = self._tasks[task_id]
        task["status"] = "failed"
        task["error"] = error
        task["failed_at"] = datetime.now().isoformat()
        
        msg = WSMessage(
            event=EventType.TASK_FAILED.value,
            data={
                "task_id": task_id,
                "error": error,
                "failed_at": task["failed_at"]
            }
        )
        
        await self.connections.send_to_user(task["user_id"], msg)
        if task.get("channel_id"):
            await self.connections.send_to_channel(task["channel_id"], msg)
    
    async def emit_notification(self, user_id: str, channel_id: str,
                               title: str, content: str, level: str = "info"):
        """Emit notification to user"""
        msg = WSMessage(
            event=EventType.NOTIFICATION.value,
            data={
                "title": title,
                "content": content,
                "level": level  # info, warning, error, success
            }
        )
        
        await self.connections.send_to_user(user_id, msg)
        if channel_id:
            await self.connections.send_to_channel(channel_id, msg)
    
    # ─────────────────────────────────────────────────────────────────
    # Task Management
    # ─────────────────────────────────────────────────────────────────
    
    def get_task(self, task_id: str) -> Optional[dict]:
        """Get task info"""
        return self._tasks.get(task_id)
    
    def get_user_tasks(self, user_id: str) -> list[dict]:
        """Get all tasks for a user"""
        return [t for t in self._tasks.values() if t["user_id"] == user_id]
    
    def get_active_tasks(self, user_id: str = None) -> list[dict]:
        """Get all active (non-completed) tasks"""
        tasks = [t for t in self._tasks.values() if t["status"] not in ["completed", "failed"]]
        if user_id:
            tasks = [t for t in tasks if t["user_id"] == user_id]
        return tasks
    
    # ─────────────────────────────────────────────────────────────────
    # Heartbeat
    # ─────────────────────────────────────────────────────────────────
    
    async def start_heartbeat(self, interval: int = 30):
        """Start heartbeat to keep connections alive"""
        while True:
            await asyncio.sleep(interval)
            try:
                await self.connections.broadcast(WSMessage(
                    event=EventType.HEARTBEAT.value,
                    data={"timestamp": datetime.now().isoformat()}
                ))
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")


# ─────────────────────────────────────────────────────────────────
# Global Instance
# ─────────────────────────────────────────────────────────────────

# Global WebSocket manager instance
_ws_manager: Optional[WebSocketManager] = None


def get_websocket_manager() -> WebSocketManager:
    """Get or create global WebSocket manager"""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


async def init_websocket_manager() -> WebSocketManager:
    """Initialize and return WebSocket manager"""
    manager = get_websocket_manager()
    # Start heartbeat in background
    asyncio.create_task(manager.start_heartbeat())
    return manager
