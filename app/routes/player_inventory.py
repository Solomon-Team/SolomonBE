from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime

from app.core.database import SessionLocal
from app.services.deps import get_current_user, require_perm
from app.models.user import User
from app.models.item import Item
from app.models.item_value import ItemValue
from app.models.inventory import PlayerInventory, PlayerInventoryLedger

router = APIRouter(prefix="/inventory/player", tags=["inventory"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------- Snapshot ----------

@router.get("/{user_id}")
def get_player_inventory(
    user_id: int,
    as_of: Optional[datetime] = Query(None, description="Optional valuation timestamp"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # Auth: self can view; otherwise need inventory.admin
    if current.id != user_id:
        require_perm("inventory.admin")(current)

    # Scope: same structure
    if not db.query(User.id).filter(User.id == user_id, User.structure_id == current.structure_id).first():
        raise HTTPException(status_code=404, detail="User not found")

    rows = (
        db.query(PlayerInventory.item_id, PlayerInventory.quantity, Item.name)
        .join(Item, Item.id == PlayerInventory.item_id)
        .filter(PlayerInventory.user_id == user_id, PlayerInventory.structure_id == current.structure_id)
        .order_by(Item.name.asc())
        .all()
    )

    # Optional valuation (use latest <= as_of; else latest overall)
    values_map = {}
    if as_of:
        subq = (
            db.query(
                ItemValue.item_id,
                func.max(ItemValue.effective_from).label("eff")
            )
            .filter(ItemValue.structure_id == current.structure_id, ItemValue.effective_from <= as_of)
            .group_by(ItemValue.item_id)
        ).subquery()

        pairs = (
            db.query(ItemValue.item_id, ItemValue.value_in_currency)
            .join(subq, (subq.c.item_id == ItemValue.item_id) & (subq.c.eff == ItemValue.effective_from))
            .all()
        )
        values_map = {pid: val for pid, val in pairs}

    items = []
    total_value = 0.0
    for item_id, qty, name in rows:
        price = float(values_map.get(item_id, 0)) if as_of else None
        value = (price * int(qty)) if price is not None else None
        if value is not None:
            total_value += value
        items.append({
            "item_id": item_id,
            "name": name,
            "quantity": int(qty),
            "price": price,
            "value": value,
        })

    return {
        "user_id": user_id,
        "structure_id": current.structure_id,
        "items": items,
        "total_value": total_value if as_of else None,
    }

# ---------- Ledger ----------

@router.get("/{user_id}/ledger")
def get_player_ledger(
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if current.id != user_id:
        require_perm("inventory.admin")(current)

    if not db.query(User.id).filter(User.id == user_id, User.structure_id == current.structure_id).first():
        raise HTTPException(status_code=404, detail="User not found")

    q = (
        db.query(
            PlayerInventoryLedger.id,
            PlayerInventoryLedger.timestamp,
            PlayerInventoryLedger.item_id,
            Item.name,
            PlayerInventoryLedger.delta_qty,
            PlayerInventoryLedger.trade_id,
            PlayerInventoryLedger.trade_line_id,
            PlayerInventoryLedger.movement_reason_code,
        )
        .join(Item, Item.id == PlayerInventoryLedger.item_id)
        .filter(PlayerInventoryLedger.user_id == user_id, PlayerInventoryLedger.structure_id == current.structure_id)
        .order_by(PlayerInventoryLedger.timestamp.desc(), PlayerInventoryLedger.id.desc())
    )
    total = q.count()
    rows = q.limit(limit).offset(offset).all()

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "rows": [
            {
                "id": r.id,
                "timestamp": r.timestamp,
                "item_id": r.item_id,
                "item_name": r.name,
                "delta_qty": int(r.delta_qty),
                "trade_id": r.trade_id,
                "trade_line_id": r.trade_line_id,
                "movement_reason_code": r.movement_reason_code,
            } for r in rows
        ]
    }
