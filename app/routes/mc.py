# app/routes/mc.py
from __future__ import annotations
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from sqlalchemy import select, and_
from datetime import datetime, timezone

from app.services.deps import get_db, require_perm
from app.schemas.mc import (
    MCEventIn, MCEventBatchIn, MCPlayerSnapshotOut, MCUuidsOut, MCUuidDetailOut, MCItemsOut
)
from app.services.mc_ingest import (
    upsert_live_player, insert_history_throttled, upsert_player_inventory_snapshot,
    upsert_container_snapshot, sha256_hex
)
from app.models.mc import MCIngestToken, MCLivePlayer, MCPlayerInventorySnapshot, MCContainerSnapshot

router = APIRouter(prefix="/mc", tags=["minecraft"])

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
def ingest_event(
    payload: MCEventIn,
    db: Session = Depends(get_db),
    x_ingest_token: str = Header(default="", alias="X-Ingest-Token"),
):
    structure_id = _resolve_structure_id_from_ingest_token(db, x_ingest_token)
    e = payload.normalized()
    upsert_live_player(db, structure_id, e, link_user=True)
    insert_history_throttled(db, structure_id, e)
    upsert_player_inventory_snapshot(db, structure_id, e)
    upsert_container_snapshot(db, structure_id, e)
    db.commit()
    return {"status": "ok"}

@router.post("/events/batch")
def ingest_events_batch(
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
        upsert_container_snapshot(db, structure_id, e)
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
