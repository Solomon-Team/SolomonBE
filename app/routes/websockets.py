# app/routes/websockets.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends
from sqlalchemy.orm import Session, joinedload
from jose import JWTError
import logging
import json
import asyncio
from datetime import datetime, timezone

from app.services.deps import get_db
from app.services.websocket_manager import WebSocketManager
from app.core.security import decode_jwt_token
from app.models.user import User

logger = logging.getLogger("bookkeeper.websocket.routes")
logger.setLevel(logging.INFO)

router = APIRouter(tags=["websocket"])


def validate_token_and_get_user(token: str, db: Session) -> User:
    """
    Validate JWT token and return the associated user.
    Raises HTTPException if invalid.
    """
    try:
        payload = decode_jwt_token(token)
        sub = payload.get("sub")
        if sub is None:
            raise ValueError("Token missing 'sub' claim")

        user_id = int(sub)
    except (JWTError, ValueError) as e:
        logger.error(f"Invalid token: {e}")
        raise ValueError(f"Invalid token: {e}")

    # Load user with eager-loaded roles
    user = (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        raise ValueError(f"User not found: {user_id}")

    return user


@router.websocket("/ws/mc")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token"),
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for Minecraft clients.

    Authentication:
    - JWT token passed as query parameter
    - Token validated before connection is accepted

    Message Protocol:
    - Sends: {"type": "connected", "user_id": X, "username": "...", "structure_id": "..."}
    - Sends: {"type": "ping", "timestamp": "..."}
    - Sends: {"type": "message", "id": X, "text": "...", "kind": "CHAT", "timestamp": "..."}
    - Receives: {"type": "pong", "timestamp": "..."}
    - Receives: {"type": "ack", "message_ids": [1, 2, 3]}
    """
    user = None
    manager = WebSocketManager.get_instance()

    try:
        # Validate token before accepting connection
        user = validate_token_and_get_user(token, db)
        logger.info(f"WebSocket auth successful for user {user.id} ({user.username})")

    except ValueError as e:
        logger.warning(f"WebSocket connection rejected: {e}")
        await websocket.close(code=1008, reason=str(e))
        return

    # Accept the WebSocket connection
    await websocket.accept()

    try:
        # Register connection in manager
        await manager.register(websocket, user)

        # Send welcome message
        welcome_message = {
            "type": "connected",
            "user_id": user.id,
            "username": user.username,
            "structure_id": user.structure_id
        }
        await websocket.send_json(welcome_message)

        # Send full chest state on connection
        from app.services.chest_sync import get_all_chests
        chests, summary = get_all_chests(db, user.structure_id)
        chest_state_message = {
            "type": "chest_full_state",
            "chests": [c.model_dump(mode="json") for c in chests],
            "summary": summary.model_dump(mode="json")
        }
        await websocket.send_json(chest_state_message)
        logger.info(f"Sent full chest state to user {user.id}: {summary.total_chests} chests")

        # Main message loop with periodic ping
        ping_interval = 30.0  # seconds
        last_ping_time = asyncio.get_event_loop().time()

        while True:
            # Calculate time until next ping
            current_time = asyncio.get_event_loop().time()
            time_since_last_ping = current_time - last_ping_time
            timeout = max(0.1, ping_interval - time_since_last_ping)

            try:
                # Wait for message with timeout
                message_text = await asyncio.wait_for(
                    websocket.receive_text(),
                    timeout=timeout
                )

                # Handle received message
                await handle_client_message(message_text, user, manager)

            except asyncio.TimeoutError:
                # Timeout reached, send ping
                ping_message = {
                    "type": "ping",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                await websocket.send_json(ping_message)
                last_ping_time = asyncio.get_event_loop().time()
                logger.debug(f"Sent ping to user {user.id}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected normally for user {user.id}")

    except Exception as e:
        logger.error(f"WebSocket error for user {user.id}: {e}", exc_info=True)

    finally:
        # Cleanup on disconnect
        if user:
            await manager.unregister(user.id)


async def handle_client_message(message_text: str, user: User, manager: WebSocketManager) -> None:
    """
    Handle messages received from WebSocket clients.

    Supported message types:
    - pong: Response to ping (updates activity)
    - ack: Acknowledgment of received messages
    """
    try:
        message = json.loads(message_text)
        message_type = message.get("type")

        if message_type == "pong":
            # Update activity timestamp
            manager.update_activity(user.id)
            logger.debug(f"Received pong from user {user.id}")

        elif message_type == "ack":
            # Handle message acknowledgment
            message_ids = message.get("message_ids", [])
            logger.info(f"User {user.id} acknowledged messages: {message_ids}")
            # Future: Update MessageRecipientStatus in database to mark as ACKED

        else:
            logger.warning(f"Unknown message type from user {user.id}: {message_type}")

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON from user {user.id}: {e}")
    except Exception as e:
        logger.error(f"Error handling message from user {user.id}: {e}", exc_info=True)
