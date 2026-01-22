# app/schemas/websocket.py
from pydantic import BaseModel, Field
from typing import Literal, List, Dict, Any
from datetime import datetime


class WSMessageBase(BaseModel):
    """Base schema for all WebSocket messages"""
    type: str = Field(..., description="Message type discriminator")


class WSMessage(WSMessageBase):
    """
    Server-to-client message broadcast.
    Displayed in Minecraft chat with [SERVER] prefix.
    """
    type: Literal["message"]
    id: int = Field(..., description="Database message ID")
    text: str = Field(..., description="Message text content")
    kind: str = Field(..., description="Display type: CHAT, TITLE, ACTIONBAR, BOSSBAR")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class WSHeartbeatPing(WSMessageBase):
    """
    Server-to-client heartbeat ping.
    Client should respond with WSHeartbeatPong.
    """
    type: Literal["ping"]
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class WSHeartbeatPong(WSMessageBase):
    """
    Client-to-server heartbeat pong response.
    Updates last_activity timestamp.
    """
    type: Literal["pong"]
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class WSAck(WSMessageBase):
    """
    Client-to-server message acknowledgment.
    Confirms successful receipt and display of messages.
    """
    type: Literal["ack"]
    message_ids: List[int] = Field(..., description="List of acknowledged message IDs")


class WSConnected(WSMessageBase):
    """
    Server-to-client welcome message.
    Sent immediately after successful WebSocket connection.
    """
    type: Literal["connected"]
    user_id: int = Field(..., description="Authenticated user ID")
    username: str = Field(..., description="Minecraft username")
    structure_id: str = Field(..., description="User's structure ID")


class WSError(WSMessageBase):
    """
    Server-to-client error notification.
    Sent when operation fails.
    """
    type: Literal["error"]
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")


class WSChestUpdate(WSMessageBase):
    """
    Server-to-client incremental chest update.
    Sent when any client opens a chest.
    """
    type: Literal["chest_update"]
    chest: dict = Field(..., description="ChestSnapshotOut serialized")
    summary: dict = Field(..., description="ChestSummaryStats serialized")


class WSChestFullState(WSMessageBase):
    """
    Server-to-client full chest state.
    Sent on initial WebSocket connection.
    """
    type: Literal["chest_full_state"]
    chests: List[dict] = Field(..., description="List of ChestSnapshotOut serialized")
    summary: dict = Field(..., description="ChestSummaryStats serialized")


class WSLoadSchematic(WSMessageBase):
    """
    Server-to-client schematic load request.
    Instructs the client (SolomonMatica) to load and place a schematic.
    """
    type: Literal["load_schematic"]
    schematic_id: str = Field(..., description="ID of the schematic to load")
    x: int = Field(..., description="X coordinate to place schematic")
    y: int = Field(..., description="Y coordinate to place schematic")
    z: int = Field(..., description="Z coordinate to place schematic")
    request_id: str = Field(..., description="Unique request ID for tracking")


class WSLoadSchematicAck(WSMessageBase):
    """
    Client-to-server acknowledgment for schematic load request.
    Reports success or failure of schematic loading.
    """
    type: Literal["load_schematic_ack"]
    request_id: str = Field(..., description="Request ID from load_schematic message")
    success: bool = Field(..., description="Whether the schematic was loaded successfully")
    error: str | None = Field(None, description="Error message if unsuccessful")


# Example usage documentation
"""
WebSocket Message Protocol Examples:

1. Connection Welcome (Server → Client):
{
    "type": "connected",
    "user_id": 123,
    "username": "Steve",
    "structure_id": "GPR"
}

2. Heartbeat Ping (Server → Client):
{
    "type": "ping",
    "timestamp": "2025-11-26T12:00:00Z"
}

3. Heartbeat Pong (Client → Server):
{
    "type": "pong",
    "timestamp": "2025-11-26T12:00:01Z"
}

4. Broadcast Message (Server → Client):
{
    "type": "message",
    "id": 456,
    "text": "Server maintenance in 5 minutes",
    "kind": "CHAT",
    "timestamp": "2025-11-26T12:00:00Z"
}

5. Message Acknowledgment (Client → Server):
{
    "type": "ack",
    "message_ids": [456, 457, 458]
}

6. Error (Server → Client):
{
    "type": "error",
    "code": "INVALID_MESSAGE",
    "message": "Message format is invalid"
}
"""
