# app/routes/mc_messages.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from fastapi import HTTPException
from sqlalchemy import and_, func
from typing import Optional, Tuple

from app.services import mc_policy
from app.models.message import Message, MessageRecipientStatus
from app.schemas.message import MCMessage, MCAckIn

from app.models.user import User
from app.models.user_profile import UserProfile                    # resolve MC user  :contentReference[oaicite:7]{index=7}
from app.models.location import Location                           # has x,y,z        :contentReference[oaicite:8]{index=8}
from app.models.item import Item                                   # auto-create      :contentReference[oaicite:9]{index=9}
from app.models import MovementReason                              # optional reason  :contentReference[oaicite:10]{index=10}
from app.services.deps import get_db, get_current_user, get_current_structure
from app.schemas.mc_trades import MCTradeIn
from app.schemas.trade import TradeCreate, TradeLineIn, TradeOut   # existing schemas  :contentReference[oaicite:5]{index=5}
from app.routes.trades import create_trade as _create_trade        # reuse creator   :contentReference[oaicite:6]{index=6}

router = APIRouter(prefix="/mc", tags=["mc"])

@router.get("/messages", response_model=List[MCMessage])
def pull_messages(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    rows = (
        db.query(Message)
        .join(
            MessageRecipientStatus,
            and_(
                MessageRecipientStatus.message_id == Message.id,
                MessageRecipientStatus.user_id == current_user.id,
            ),
        )
        .filter(
            Message.structure_id == current_user.structure_id,
            MessageRecipientStatus.status.in_(["QUEUED", "FAILED"]),
            (Message.deliver_after.is_(None) | (Message.deliver_after <= now)),
            (Message.expires_at.is_(None) | (Message.expires_at > now)),
        )
        .order_by(Message.priority.desc(), Message.id.asc())
        .limit(100)
        .all()
    )

    # Resolve positions in batch (by kind) for this structure
    kinds: List[str] = list({r.kind for r in rows})
    kind_to_pos: Dict[str, str] = {}
    for k in kinds:
        kind_to_pos[k] = mc_policy.get_position(db, current_user.structure_id, k)

    return [
        MCMessage(
            id=r.id,
            text=r.text,
            kind=r.kind,
            meta=r.meta or {},
            expires_at=r.expires_at,
            priority=r.priority,
            created_at=r.created_at,
            position=kind_to_pos.get(r.kind, "LEFT"),
        )
        for r in rows
    ]

@router.post("/messages/ack")
def ack_messages(payload: MCAckIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    changed = 0
    now = datetime.now(timezone.utc)
    # delivered -> ACKED
    if payload.delivered:
        q = db.query(MessageRecipientStatus).filter(
            MessageRecipientStatus.user_id == current_user.id,
            MessageRecipientStatus.message_id.in_(payload.delivered),
        )
        for row in q.all():
            row.status = "ACKED"
            row.updated_at = now
            changed += 1
    # failed -> FAILED (+attempt_count)
    if payload.failed:
        q = db.query(MessageRecipientStatus).filter(
            MessageRecipientStatus.user_id == current_user.id,
            MessageRecipientStatus.message_id.in_(payload.failed),
        )
        for row in q.all():
            row.status = "FAILED"
            row.attempt_count = (row.attempt_count or 0) + 1
            row.updated_at = now
            changed += 1
    db.commit()
    return {"updated": changed}


def _find_trader_by_mc(db: Session, structure_id: str, mc_username: str) -> User:
    row = (
        db.query(User)
        .join(UserProfile, UserProfile.user_id == User.id)
        .filter(
            User.structure_id == structure_id,
            func.lower(UserProfile.minecraft_username) == func.lower(mc_username),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Player (minecraft_username) not found in your structure")
    return row

def _get_or_create_unknown_location(db: Session, structure_id: str) -> Location:
    loc = (
        db.query(Location)
        .filter(
            Location.structure_id == structure_id,
            func.lower(Location.name) == func.lower("Unknown location"),
        )
        .first()
    )
    if loc:
        return loc
    loc = Location(
        structure_id=structure_id,
        name="Unknown location",
        code="UNKNOWN",
        type="OTHER",
        description="Auto-created fallback for MC trades when no nearby location is found",
        is_active=True,
    )
    db.add(loc); db.flush()
    return loc

def _nearest_location_within(db: Session, structure_id: str, x: int, y: int, z: int, radius: int = 100) -> Optional[Location]:
    q = (
        db.query(Location)
        .filter(
            Location.structure_id == structure_id,
            Location.x.isnot(None), Location.y.isnot(None), Location.z.isnot(None),
            Location.x.between(x - radius, x + radius),
            Location.y.between(y - radius, y + radius),
            Location.z.between(z - radius, z + radius),
        )
    )
    candidates = q.all()
    best: Tuple[Optional[Location], Optional[int]] = (None, None)
    r2 = radius * radius
    for loc in candidates:
        dx = (loc.x or 0) - x
        dy = (loc.y or 0) - y
        dz = (loc.z or 0) - z
        d2 = dx*dx + dy*dy + dz*dz
        if d2 <= r2 and (best[1] is None or d2 < best[1]):
            best = (loc, d2)
    return best[0]

def _find_or_create_item(db: Session, creator_user_id: int, name: Optional[str], code: Optional[str]) -> Item:
    if code:
        it = db.query(Item).filter(func.lower(Item.code) == func.lower(code)).first()
        if it: return it
    if name:
        it = db.query(Item).filter(func.lower(Item.name) == func.lower(name)).first()
        if it: return it
    base_code = (code or (name or "ITEM")).upper().replace(" ", "_")[0:60] or "ITEM"
    final_code = base_code
    i = 2
    while db.query(Item.id).filter(Item.code == final_code).first() is not None:
        suffix = f"_{i}"
        final_code = (base_code[: max(1, 60 - len(suffix))] + suffix)
        i += 1
    it = Item(
        name=name or code or "Unnamed Item",
        code=final_code,
        category="MC_IMPORT",
        created_by_user_id=creator_user_id,
    )
    db.add(it); db.flush()
    return it

def _maybe_reason(db: Session, structure_id: str, code: str) -> Optional[str]:
    ok = db.query(MovementReason.id).filter(
        MovementReason.structure_id == structure_id,
        MovementReason.code == code,
        MovementReason.is_active.is_(True),
    ).first()
    return code if ok else None

@router.post("/trades", response_model=TradeOut)
def create_mc_trade(
    payload: MCTradeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    structure_id: str = Depends(get_current_structure),
):
    """
    Create ONE trade with N lines from Minecraft JSON, using JWT for identity.
    direction 'FROM' => items FROM player TO location -> line.direction = 'GAINED'
    direction 'TO'   => items FROM location TO player -> line.direction = 'GIVEN'
    """
    trader = _find_trader_by_mc(db, structure_id, payload.player_mc_username)

    chest = payload.chest
    loc = _nearest_location_within(db, structure_id, chest.x, chest.y, chest.z, radius=100)
    if not loc:
        loc = _get_or_create_unknown_location(db, structure_id)

    header_from_loc = loc.id if payload.direction == "TO" else None
    header_to_loc   = loc.id if payload.direction == "FROM" else None

    lines: list[TradeLineIn] = []
    for item_in in payload.items:
        it = _find_or_create_item(db, current_user.id, item_in.name, item_in.code)
        if payload.direction == "FROM":
            # player -> location
            dir_lbl = "GAINED"
            reason  = _maybe_reason(db, structure_id, dir_lbl)
            ln = TradeLineIn(
                item_id=it.id,
                direction=dir_lbl,
                quantity=item_in.amount,
                from_user_id=trader.id,
                to_user_id=None,
                movement_reason_code=reason,
            )
        else:
            # location -> player
            dir_lbl = "GIVEN"
            reason  = _maybe_reason(db, structure_id, dir_lbl)
            ln = TradeLineIn(
                item_id=it.id,
                direction=dir_lbl,
                quantity=item_in.amount,
                from_user_id=None,
                to_user_id=trader.id,
                movement_reason_code=reason,
            )
        lines.append(ln)

    tc = TradeCreate(
        timestamp=datetime.now(timezone.utc),
        from_location_id=header_from_loc,
        to_location_id=header_to_loc,
        lines=lines,
    )

    # Reuse your canonical creator (validations + ledgers/inventory updates)
    return _create_trade(payload=tc, db=db, user=current_user, structure_id=structure_id)