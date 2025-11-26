# app/services/websocket_manager.py
from dataclasses import dataclass
from typing import Dict, Set, Optional
from datetime import datetime, timezone
from fastapi import WebSocket
import logging
import json

from app.models.user import User

logger = logging.getLogger("bookkeeper.websocket")
logger.setLevel(logging.INFO)


@dataclass
class ConnectionInfo:
    """Information about an active WebSocket connection"""
    websocket: WebSocket
    user_id: int
    structure_id: str
    mc_uuid: str
    username: str
    connected_at: datetime
    last_activity: datetime


class WebSocketManager:
    """
    Singleton manager for WebSocket connections.
    Tracks active connections and provides broadcast capabilities.
    """
    _instance: Optional['WebSocketManager'] = None

    def __init__(self):
        if WebSocketManager._instance is not None:
            raise RuntimeError("WebSocketManager is a singleton. Use get_instance()")

        self.connections: Dict[int, ConnectionInfo] = {}
        self.structure_index: Dict[str, Set[int]] = {}
        logger.info("WebSocketManager initialized")

    @classmethod
    def get_instance(cls) -> 'WebSocketManager':
        """Get the singleton instance of WebSocketManager"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def register(self, websocket: WebSocket, user: User) -> None:
        """
        Register a new WebSocket connection.
        If user already has a connection, closes the old one first.
        """
        # Close existing connection if any
        if user.id in self.connections:
            logger.info(f"Closing existing connection for user {user.id}")
            await self.unregister(user.id)

        # Create connection info
        now = datetime.now(timezone.utc)
        conn_info = ConnectionInfo(
            websocket=websocket,
            user_id=user.id,
            structure_id=user.structure_id,
            mc_uuid=user.mc_uuid,
            username=user.username,
            connected_at=now,
            last_activity=now
        )

        # Add to connections
        self.connections[user.id] = conn_info

        # Add to structure index
        if user.structure_id not in self.structure_index:
            self.structure_index[user.structure_id] = set()
        self.structure_index[user.structure_id].add(user.id)

        logger.info(
            f"WebSocket connected: user_id={user.id}, username={user.username}, "
            f"structure={user.structure_id}, total_connections={len(self.connections)}"
        )

    async def unregister(self, user_id: int) -> None:
        """Remove a WebSocket connection and clean up indexes"""
        if user_id not in self.connections:
            return

        conn_info = self.connections[user_id]

        # Remove from structure index
        if conn_info.structure_id in self.structure_index:
            self.structure_index[conn_info.structure_id].discard(user_id)
            # Clean up empty structure sets
            if not self.structure_index[conn_info.structure_id]:
                del self.structure_index[conn_info.structure_id]

        # Remove from connections
        del self.connections[user_id]

        logger.info(
            f"WebSocket disconnected: user_id={user_id}, username={conn_info.username}, "
            f"total_connections={len(self.connections)}"
        )

    async def send_to_user(self, user_id: int, message: dict) -> bool:
        """
        Send a message to a specific user's WebSocket.
        Returns True if sent successfully, False if user not connected.
        """
        if user_id not in self.connections:
            return False

        conn_info = self.connections[user_id]

        try:
            await conn_info.websocket.send_json(message)
            conn_info.last_activity = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            # Connection likely dead, clean up
            await self.unregister(user_id)
            return False

    async def broadcast_to_structure(self, structure_id: str, message: dict) -> int:
        """
        Broadcast a message to all users in a specific structure.
        Returns count of successful deliveries.
        """
        if structure_id not in self.structure_index:
            logger.warning(f"No connections for structure {structure_id}")
            return 0

        user_ids = list(self.structure_index[structure_id])  # Copy to avoid modification during iteration
        sent_count = 0

        for user_id in user_ids:
            success = await self.send_to_user(user_id, message)
            if success:
                sent_count += 1

        logger.info(f"Broadcast to structure {structure_id}: sent to {sent_count}/{len(user_ids)} users")
        return sent_count

    async def broadcast_to_all(self, message: dict) -> int:
        """
        Broadcast a message to all connected users.
        Returns count of successful deliveries.
        """
        user_ids = list(self.connections.keys())  # Copy to avoid modification during iteration
        sent_count = 0

        for user_id in user_ids:
            success = await self.send_to_user(user_id, message)
            if success:
                sent_count += 1

        logger.info(f"Broadcast to all: sent to {sent_count}/{len(user_ids)} users")
        return sent_count

    def get_connection_count(self) -> int:
        """Get total number of active connections"""
        return len(self.connections)

    def get_structure_connection_count(self, structure_id: str) -> int:
        """Get number of connections for a specific structure"""
        return len(self.structure_index.get(structure_id, set()))

    def is_connected(self, user_id: int) -> bool:
        """Check if a user has an active WebSocket connection"""
        return user_id in self.connections

    def update_activity(self, user_id: int) -> None:
        """Update last activity timestamp for a user"""
        if user_id in self.connections:
            self.connections[user_id].last_activity = datetime.now(timezone.utc)

    async def cleanup_stale_connections(self, timeout_seconds: int = 60) -> int:
        """
        Remove connections that have been inactive for more than timeout_seconds.
        Returns count of cleaned up connections.
        """
        now = datetime.now(timezone.utc)
        stale_user_ids = []

        for user_id, conn_info in self.connections.items():
            inactive_seconds = (now - conn_info.last_activity).total_seconds()
            if inactive_seconds > timeout_seconds:
                stale_user_ids.append(user_id)

        for user_id in stale_user_ids:
            logger.warning(f"Cleaning up stale connection for user {user_id}")
            await self.unregister(user_id)

        if stale_user_ids:
            logger.info(f"Cleaned up {len(stale_user_ids)} stale connections")

        return len(stale_user_ids)

    def get_connection_info(self, user_id: int) -> Optional[ConnectionInfo]:
        """Get connection info for a specific user"""
        return self.connections.get(user_id)

    def get_all_connections(self) -> list[ConnectionInfo]:
        """Get list of all active connections"""
        return list(self.connections.values())
