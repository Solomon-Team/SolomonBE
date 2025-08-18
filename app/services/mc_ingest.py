# app/services/mc_ingest.py
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from typing import Optional, Iterable
from sqlalchemy.orm import Session
from sqlalchemy import select, update, insert, func, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.models.mc import (
    MCIngestToken, MCLivePlayer, MCPositionHistory,
    MCPlayerInventorySnapshot, MCContainerSnapshot
)
from app.schemas.mc import MCEventNorm
from hashlib import sha256

# Adjust this import if your profile model lives elsewhere:
# from app.models.user_profile import UserProfile
from app.models.user import User  # for FK only
from app.models.user_profile import UserProfile  # adjust if needed

HISTORY_MIN_INTERVAL_S = 2  # throttle: store at most once per 2s per uuid

def sha256_hex(s: str) -> str:
    return sha256(s.encode("utf-8")).hexdigest()

def resolve_user_link(db: Session, structure_id: str, uuid: str, username: str) -> Optional[int]:
    """
    Link a Minecraft identity to an internal user_id, scoped by users.structure_id.
    Works even if user_profiles has NO 'minecraft_uuid' column (username-only linking).
    If the column exists, we'll try that first.
    """
    # Try UUID (only if the column exists and uuid provided)
    uuid_col = getattr(UserProfile, "minecraft_uuid", None)
    if uuid and uuid_col is not None:
        q1 = (
            select(UserProfile.user_id)
            .join(User, User.id == UserProfile.user_id)
            .where(
                and_(
                    User.structure_id == structure_id,
                    func.lower(uuid_col) == func.lower(uuid),
                )
            )
            .limit(1)
        )
        r1 = db.execute(q1).scalar_one_or_none()
        if r1 is not None:
            return int(r1)

    # Fallback: username (case-insensitive)
    name_col = getattr(UserProfile, "minecraft_username", None)
    if username and name_col is not None:
        q2 = (
            select(UserProfile.user_id)
            .join(User, User.id == UserProfile.user_id)
            .where(
                and_(
                    User.structure_id == structure_id,
                    func.lower(name_col) == func.lower(username),
                )
            )
            .limit(1)
        )
        r2 = db.execute(q2).scalar_one_or_none()
        if r2 is not None:
            return int(r2)

    return None

def upsert_live_player(db: Session, structure_id: str, e: MCEventNorm, link_user: bool = True) -> int | None:
    user_id = resolve_user_link(db, structure_id, e.uuid, e.username) if link_user else None

    insert_stmt = pg_insert(MCLivePlayer).values(
        structure_id=structure_id,
        uuid=e.uuid,
        username=e.username,
        x=e.x, y=e.y, z=e.z,
        last_seen_at=e.ts,
        hp_json=e.hp,
        inventory_json=e.inventory,
        user_id=user_id,
    )
    update_stmt = insert_stmt.on_conflict_do_update(
        index_elements=["structure_id", "uuid"],
        set_={
            "username": e.username,
            "x": e.x, "y": e.y, "z": e.z,
            "last_seen_at": e.ts,
            "hp_json": func.coalesce(insert_stmt.excluded.hp_json, MCLivePlayer.hp_json),
            "inventory_json": func.coalesce(insert_stmt.excluded.inventory_json, MCLivePlayer.inventory_json),
            "user_id": func.coalesce(insert_stmt.excluded.user_id, MCLivePlayer.user_id),
        },
    )
    db.execute(update_stmt)
    return user_id

def insert_history_throttled(db: Session, structure_id: str, e: MCEventNorm):
    # throttle: if last history point for (uuid) is < 2s ago, skip
    last_ts = db.execute(
        select(MCPositionHistory.ts)
        .where(and_(MCPositionHistory.structure_id == structure_id, MCPositionHistory.uuid == e.uuid))
        .order_by(MCPositionHistory.ts.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last_ts and (e.ts - last_ts) < timedelta(seconds=HISTORY_MIN_INTERVAL_S):
        return
    db.add(MCPositionHistory(structure_id=structure_id, uuid=e.uuid, ts=e.ts, x=e.x, y=e.y, z=e.z))

def upsert_player_inventory_snapshot(db: Session, structure_id: str, e: MCEventNorm):
    if e.inventory is None and e.hp is None:
        return
    insert_stmt = pg_insert(MCPlayerInventorySnapshot).values(
        structure_id=structure_id, uuid=e.uuid,
        inventory_json=e.inventory, hp_json=e.hp, last_seen_at=e.ts
    )
    db.execute(insert_stmt.on_conflict_do_update(
        index_elements=["structure_id", "uuid"],
        set_={
            "inventory_json": func.coalesce(insert_stmt.excluded.inventory_json, MCPlayerInventorySnapshot.inventory_json),
            "hp_json": func.coalesce(insert_stmt.excluded.hp_json, MCPlayerInventorySnapshot.hp_json),
            "last_seen_at": e.ts
        }
    ))

def upsert_container_snapshot(db: Session, structure_id: str, e: MCEventNorm):
    if not e.container or "pos" not in e.container:
        return
    pos = e.container.get("pos") or e.container.get("Pos") or e.container.get("position")
    try:
        cx, cy, cz = int(pos[0]), int(pos[1]), int(pos[2])
    except Exception:
        return
    items = e.container.get("items")
    signs = e.signs
    insert_stmt = pg_insert(MCContainerSnapshot).values(
        structure_id=structure_id, x=cx, y=cy, z=cz,
        items_json=items, signs_json=signs,
        opened_by_uuid=e.uuid, opened_by_username=e.username,
        last_seen_at=e.ts
    )
    db.execute(insert_stmt.on_conflict_do_update(
        index_elements=["structure_id", "x", "y", "z"],
        set_={
            "items_json": func.coalesce(insert_stmt.excluded.items_json, MCContainerSnapshot.items_json),
            "signs_json": func.coalesce(insert_stmt.excluded.signs_json, MCContainerSnapshot.signs_json),
            "opened_by_uuid": e.uuid,
            "opened_by_username": e.username,
            "last_seen_at": e.ts
        }
    ))
