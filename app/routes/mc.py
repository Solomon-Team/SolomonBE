# app/routes/mc.py
from __future__ import annotations
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from datetime import datetime, timezone

from app.models import UserProfile
from app.services.deps import get_db, require_perm, get_current_user
from app.schemas.mc import (
    MCEventIn, MCEventBatchIn, MCPlayerSnapshotOut, MCUuidsOut, MCUuidDetailOut, MCItemsOut
)
from app.services.mc_ingest import (
    upsert_live_player, insert_history_throttled, upsert_player_inventory_snapshot,
    upsert_container_snapshot, sha256_hex
)
from app.models.mc import MCIngestToken, MCLivePlayer, MCPlayerInventorySnapshot, MCContainerSnapshot

logger = logging.getLogger("bookkeeper.mc.routes")
logger.setLevel(logging.INFO)

router = APIRouter(prefix="/api/mc", tags=["minecraft"])

# ---------- Helpers ----------
def _resolve_structure_id_from_ingest_token(db: Session, token: str) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="Missing X-Ingest-Token")
    token_hash = sha256_hex(token)
    row = db.execute(
        select(MCIngestToken).where(
            and_(MCIngestToken.token_sha256 == token_hash, MCIngestToken.active == True)  # noqa
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid token")
    row.last_used_at = datetime.now(timezone.utc)
    db.add(row)
    return str(row.structure_id)

# ---------- Ingest ----------
@router.post("/events")
async def ingest_event(
    payload: MCEventIn,
    db: Session = Depends(get_db),
    x_ingest_token: str = Header(default="", alias="X-Ingest-Token"),
):
    structure_id = _resolve_structure_id_from_ingest_token(db, x_ingest_token)
    e = payload.normalized()
    upsert_live_player(db, structure_id, e, link_user=True)
    insert_history_throttled(db, structure_id, e)
    upsert_player_inventory_snapshot(db, structure_id, e)
    await upsert_container_snapshot(db, structure_id, e)
    db.commit()
    return {"status": "ok"}

@router.post("/events/batch")
async def ingest_events_batch(
    payload: MCEventBatchIn,
    db: Session = Depends(get_db),
    x_ingest_token: str = Header(default="", alias="X-Ingest-Token"),
):
    structure_id = _resolve_structure_id_from_ingest_token(db, x_ingest_token)
    accepted = 0
    for raw in payload.events[:100]:
        e = raw.normalized()
        upsert_live_player(db, structure_id, e, link_user=True)
        insert_history_throttled(db, structure_id, e)
        upsert_player_inventory_snapshot(db, structure_id, e)
        await upsert_container_snapshot(db, structure_id, e)
        accepted += 1
    db.commit()
    return {"status": "ok", "accepted": accepted}

# ---------- Read (admin-only, structure-scoped) ----------
@router.get("/positions/snapshot", response_model=List[MCPlayerSnapshotOut])
def positions_snapshot(
    since: datetime | None = None,
    limit: int = 1000,
    db: Session = Depends(get_db),
    current_user = Depends(require_perm("users.admin")),
):
    structure_id = current_user.structure_id
    q = select(MCLivePlayer).where(MCLivePlayer.structure_id == structure_id)
    if since:
        q = q.where(MCLivePlayer.last_seen_at >= since)
    q = q.order_by(MCLivePlayer.last_seen_at.desc()).limit(limit)
    rows = db.execute(q).scalars().all()
    return [
        MCPlayerSnapshotOut(
            uuid=r.uuid, username=r.username, x=r.x, y=r.y, z=r.z,
            ts=r.last_seen_at, user_id=r.user_id
        ) for r in rows
    ]

@router.get("/uuids", response_model=MCUuidsOut)
def list_uuids(
    db: Session = Depends(get_db),
    current_user = Depends(require_perm("users.admin")),
):
    structure_id = current_user.structure_id
    rows = db.execute(
        select(MCLivePlayer.uuid, MCLivePlayer.username).where(MCLivePlayer.structure_id == structure_id)
    ).all()
    return {"players": {uuid: name for (uuid, name) in rows}}

@router.get("/uuid/{uuid}", response_model=MCUuidDetailOut)
def uuid_detail(
    uuid: str,
    db: Session = Depends(get_db),
    current_user = Depends(require_perm("users.admin")),
):
    structure_id = current_user.structure_id
    lp = db.execute(
        select(MCLivePlayer).where(
            and_(MCLivePlayer.structure_id == structure_id, MCLivePlayer.uuid == uuid.lower())
        )
    ).scalar_one_or_none()
    if not lp:
        return {"uuid": uuid, "snapshot": {}}
    snap = {
        "username": lp.username,
        "last_seen_at": lp.last_seen_at.isoformat(),
        "pos": [lp.x, lp.y, lp.z],
        "hp": lp.hp_json,
        "inventory": lp.inventory_json,
    }
    return {"uuid": uuid, "snapshot": snap}

@router.get("/items", response_model=MCItemsOut)
def items_dump(
    db: Session = Depends(get_db),
    current_user = Depends(require_perm("users.admin")),
):
    structure_id = current_user.structure_id
    inv_rows = db.execute(
        select(MCPlayerInventorySnapshot).where(MCPlayerInventorySnapshot.structure_id == structure_id)
    ).scalars().all()
    players = {
        r.uuid: {"inventory": r.inventory_json, "last_seen_at": r.last_seen_at.isoformat()}
        for r in inv_rows
    }
    chest_rows = db.execute(
        select(MCContainerSnapshot).where(MCContainerSnapshot.structure_id == structure_id)
    ).scalars().all()
    chests = {
        f"{r.x},{r.y},{r.z}": {
            "items": r.items_json,
            "signs": r.signs_json,
            "opened_by": {"uuid": r.opened_by_uuid, "username": r.opened_by_username},
            "last_seen_at": r.last_seen_at.isoformat(),
        }
        for r in chest_rows
    }
    return {"players": players, "chests": chests}


@router.get("/chests")
def get_chests(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """
    Get complete list of all known chests in user's structure.

    **Authentication**: JWT required (any authenticated user)

    **Use Cases**:
    - Initial data load for client applications
    - Recovery from faulty WebSocket data
    - Polling fallback (though WebSocket is preferred)

    **Returns**:
    - `chests`: Array of chest snapshots with coordinates, items, signs
    - `summary`: Aggregate statistics (total chests, last update, item counts)
    """
    from app.services.chest_sync import get_all_chests
    from app.schemas.mc import ChestListOut

    structure_id = current_user.structure_id
    chests, summary = get_all_chests(db, structure_id)

    return ChestListOut(chests=chests, summary=summary)

@router.post("/events/jwt")
async def ingest_event_jwt(
    payload: MCEventIn,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),  # any authenticated user
):
    # derive scope from JWT
    structure_id = current_user.structure_id
    # display name preference: profile.minecraft_username if present
    prof = db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id)).scalar_one_or_none()
    preferred_name = (prof.minecraft_username if prof and getattr(prof, "minecraft_username", None) else None)

    e = payload.normalized()

    # Log container events for debugging
    if e.container:
        logger.info(f"Container event from {e.username} at ({e.x}, {e.y}, {e.z})")
        logger.debug(f"Container has {len(e.container)} keys: {list(e.container.keys())}")

    # force link to this user, override display username if we have one
    upsert_live_player(
        db,
        structure_id,
        e,
        link_user=False,
        force_user_id=current_user.id,
        display_username_override=preferred_name
    )
    insert_history_throttled(db, structure_id, e)
    upsert_player_inventory_snapshot(db, structure_id, e)
    await upsert_container_snapshot(db, structure_id, e)
    db.commit()
    return {"status": "ok"}