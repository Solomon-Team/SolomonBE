# app/routes/mc_broadcast.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
import logging

from app.services.deps import get_db, require_perm
from app.services.websocket_manager import WebSocketManager
from app.models.user import User
from app.models.message import Message

logger = logging.getLogger("bookkeeper.broadcast")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/mc", tags=["mc-broadcast"])


class BroadcastMessageIn(BaseModel):
    """Request schema for broadcast endpoint"""
    text: str = Field(..., min_length=1, max_length=1000, description="Message text to broadcast")
    kind: str = Field(default="CHAT", description="Message display type: CHAT, TITLE, ACTIONBAR, BOSSBAR")
    target_structure_id: Optional[str] = Field(None, description="Target structure ID (None = all structures)")


class BroadcastMessageOut(BaseModel):
    """Response schema for broadcast endpoint"""
    message_id: int
    sent_count: int
    total_connections: int
    timestamp: datetime


@router.post("/broadcast", response_model=BroadcastMessageOut, status_code=202)
async def broadcast_message(
    payload: BroadcastMessageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_perm("users.admin"))
):
    """
    Broadcast a message to all connected Minecraft clients via WebSocket.

    **Permissions**: Requires `users.admin` permission

    **Request Body**:
    - `text`: Message text (1-1000 characters)
    - `kind`: Display type (CHAT, TITLE, ACTIONBAR, BOSSBAR) - default: CHAT
    - `target_structure_id`: Optional structure filter (null = broadcast to all)

    **Response** (HTTP 202 Accepted):
    - `message_id`: Database ID of the created message
    - `sent_count`: Number of clients that received the message
    - `total_connections`: Total active WebSocket connections
    - `timestamp`: Message creation timestamp

    **Message Display**:
    - Messages appear in Minecraft chat with `[SERVER]` prefix in gold color
    - Action bar messages shown above hotbar
    - Title messages displayed center screen

    **Example**:
    ```json
    {
        "text": "Server maintenance in 5 minutes",
        "kind": "CHAT"
    }
    ```
    """
    logger.info(
        f"Broadcast request from user {user.id} ({user.username}): "
        f"text='{payload.text}', kind={payload.kind}, target_structure={payload.target_structure_id}"
    )

    # Create Message record in database for audit trail
    msg = Message(
        structure_id=user.structure_id,
        text=payload.text,
        kind=payload.kind,
        created_by_user_id=user.id
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # Format WebSocket message
    ws_message = {
        "type": "message",
        "id": msg.id,
        "text": payload.text,
        "kind": payload.kind,
        "timestamp": msg.created_at.isoformat()
    }

    # Broadcast via WebSocketManager
    manager = WebSocketManager.get_instance()

    if payload.target_structure_id:
        # Broadcast to specific structure
        sent_count = await manager.broadcast_to_structure(payload.target_structure_id, ws_message)
    else:
        # Broadcast to all connected clients
        sent_count = await manager.broadcast_to_all(ws_message)

    total_connections = manager.get_connection_count()

    logger.info(
        f"Broadcast complete: message_id={msg.id}, sent={sent_count}/{total_connections}, "
        f"kind={payload.kind}, structure={payload.target_structure_id or 'ALL'}"
    )

    return BroadcastMessageOut(
        message_id=msg.id,
        sent_count=sent_count,
        total_connections=total_connections,
        timestamp=msg.created_at
    )


@router.get("/broadcast/status", tags=["mc-broadcast"])
def get_broadcast_status(
    user: User = Depends(require_perm("users.admin"))
):
    """
    Get current WebSocket connection status.

    **Permissions**: Requires `users.admin` permission

    **Returns**:
    - Total active connections
    - Connections per structure
    - List of connected users

    **Example Response**:
    ```json
    {
        "total_connections": 5,
        "by_structure": {
            "GPR": 3,
            "OTHER": 2
        },
        "connections": [
            {
                "user_id": 1,
                "username": "player1",
                "structure_id": "GPR",
                "connected_at": "2025-11-26T12:00:00Z",
                "last_activity": "2025-11-26T12:05:00Z"
            }
        ]
    }
    ```
    """
    manager = WebSocketManager.get_instance()
    connections = manager.get_all_connections()

    # Group by structure
    by_structure = {}
    for conn in connections:
        structure_id = conn.structure_id
        by_structure[structure_id] = by_structure.get(structure_id, 0) + 1

    return {
        "total_connections": len(connections),
        "by_structure": by_structure,
        "connections": [
            {
                "user_id": conn.user_id,
                "username": conn.username,
                "mc_uuid": conn.mc_uuid,
                "structure_id": conn.structure_id,
                "connected_at": conn.connected_at.isoformat(),
                "last_activity": conn.last_activity.isoformat()
            }
            for conn in connections
        ]
    }
