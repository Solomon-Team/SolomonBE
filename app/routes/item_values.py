from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.services.deps import get_db, get_current_user, require_perm
from app.models.user import User
from app.models.item_value import ItemValue
from app.models.item import Item
from app.schemas.item_value import ItemValueCreate, ItemValueOut
from decimal import Decimal

router = APIRouter(prefix="/item-values", tags=["item-values"])

manage_vals = require_perm("valuations.manage")

@router.post("", response_model=ItemValueOut, status_code=201)
def create_value(payload: ItemValueCreate, db: Session = Depends(get_db), user: User = Depends(manage_vals)):
    item = db.query(Item).get(payload.item_id)
    if not item or not item.is_active:
        raise HTTPException(400, "Invalid item")

    v = Decimal(str(payload.value_in_currency))
    if v < Decimal("0.001") or v > Decimal("1000000"):
        raise HTTPException(400, "value_in_currency out of allowed range")

    row = ItemValue(
        structure_id=user.structure_id,
        item_id=item.id,
        value_in_currency=v,
        effective_from=payload.effective_from,
        created_by_user_id=user.id,
    )
    db.add(row); db.commit(); db.refresh(row)

    return {
        "id": row.id,
        "structure_id": row.structure_id,
        "item_id": row.item_id,
        "value_in_currency": str(row.value_in_currency),
        "effective_from": row.effective_from,
    }

@router.get("", response_model=List[ItemValueOut])
def list_values(
    item_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = db.query(ItemValue).filter(ItemValue.structure_id == user.structure_id)
    if item_id:
        q = q.filter(ItemValue.item_id == item_id)
    rows = q.order_by(ItemValue.item_id.asc(), ItemValue.effective_from.desc()).all()

    return [
        {
            "id": r.id,
            "structure_id": r.structure_id,
            "item_id": r.item_id,
            "value_in_currency": str(r.value_in_currency),
            "effective_from": r.effective_from,
        }
        for r in rows
    ]
