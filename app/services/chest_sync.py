# app/services/chest_sync.py
from __future__ import annotations
import logging
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.models.chest_sync import ChestSyncSnapshot, ChestSyncHistory
from app.schemas.mc import ChestSnapshotOut, ChestSummaryStats
from app.services.websocket_manager import WebSocketManager

logger = logging.getLogger("bookkeeper.chest_sync")
logger.setLevel(logging.INFO)


async def broadcast_chest_update(
    db: Session,
    structure_id: str,
    x: int,
    y: int,
    z: int,
    filter_callback: Optional[callable] = None
) -> int:
    """
    Broadcast incremental chest update to all connected clients in structure.

    Args:
        db: Database session
        structure_id: Structure to broadcast to
        x, y, z: Chest coordinates
        filter_callback: Optional function(user_id) -> bool for future filtering

    Returns:
        Number of clients that received the update
    """
    # Fetch the updated chest
    container = db.execute(
        select(ChestSyncSnapshot).where(
            ChestSyncSnapshot.structure_id == structure_id,
            ChestSyncSnapshot.x == x,
            ChestSyncSnapshot.y == y,
            ChestSyncSnapshot.z == z
        )
    ).scalar_one_or_none()

    if not container:
        logger.warning(f"Chest not found for broadcast: {structure_id} @ ({x},{y},{z})")
        return 0

    # Calculate summary stats
    summary = calculate_chest_summary(db, structure_id)

    # Format WebSocket message
    chest_data = ChestSnapshotOut.from_model(container)
    ws_message = {
        "type": "chest_update",
        "chest": chest_data.model_dump(mode="json"),
        "summary": summary.model_dump(mode="json")
    }

    # Broadcast to structure
    manager = WebSocketManager.get_instance()

    if filter_callback:
        # Future: custom filtering (role-based, location-based)
        # For now, just broadcast to all
        sent_count = await manager.broadcast_to_structure(structure_id, ws_message)
    else:
        sent_count = await manager.broadcast_to_structure(structure_id, ws_message)

    logger.info(
        f"Chest update broadcast: structure={structure_id}, coords=({x},{y},{z}), "
        f"sent={sent_count}"
    )

    return sent_count


def calculate_chest_summary(db: Session, structure_id: str) -> ChestSummaryStats:
    """Calculate summary statistics for all chests in structure"""
    # Count total chests
    total_chests = db.execute(
        select(func.count(ChestSyncSnapshot.id)).where(
            ChestSyncSnapshot.structure_id == structure_id
        )
    ).scalar() or 0

    # Get most recent update
    last_updated = db.execute(
        select(func.max(ChestSyncSnapshot.last_seen_at)).where(
            ChestSyncSnapshot.structure_id == structure_id
        )
    ).scalar()

    # Calculate total item slots using denormalized field
    total_slots = db.execute(
        select(func.sum(ChestSyncSnapshot.item_count)).where(
            ChestSyncSnapshot.structure_id == structure_id
        )
    ).scalar() or 0

    return ChestSummaryStats(
        total_chests=int(total_chests),
        last_updated_at=last_updated,
        total_item_slots=int(total_slots)
    )


def get_all_chests(db: Session, structure_id: str) -> tuple[list[ChestSnapshotOut], ChestSummaryStats]:
    """
    Get all chests for a structure with summary stats.
    Used for initial connection and REST endpoint.
    """
    containers = db.execute(
        select(ChestSyncSnapshot)
        .where(ChestSyncSnapshot.structure_id == structure_id)
        .order_by(ChestSyncSnapshot.last_seen_at.desc())
    ).scalars().all()

    chest_list = [ChestSnapshotOut.from_model(c) for c in containers]
    summary = calculate_chest_summary(db, structure_id)

    return chest_list, summary


def calculate_item_count(items_json: dict | None) -> int:
    """
    Calculate number of items in a chest from items_json.

    This helper handles various item JSON structures that might come from Minecraft.
    """
    if not items_json or not isinstance(items_json, dict):
        return 0

    # Handle different possible structures
    if "items" in items_json and isinstance(items_json["items"], list):
        # Structure: {"items": [{"slot": 0, "id": "...", "count": X}, ...]}
        return len(items_json["items"])
    elif "items" in items_json and isinstance(items_json["items"], dict):
        # Structure: {"items": {"slot_0": {...}, "slot_1": {...}}}
        return len(items_json["items"])
    elif isinstance(items_json, list):
        # Structure: [{"slot": 0, "id": "...", "count": X}, ...]
        return len(items_json)
    else:
        # Structure: {"slot_0": {...}, "slot_1": {...}, ...}
        # Count keys that look like slots
        return len([k for k in items_json.keys() if k.startswith("slot_") or k.isdigit()])
