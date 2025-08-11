from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from app.services.deps import get_db, get_current_user, require_perm
from app.models.user import User
from app.models.item import Item
from app.schemas.item import ItemCreate, ItemUpdate, ItemOut
from app.services.codegen import generate_unique_item_code

router = APIRouter(prefix="/items", tags=["items"])

manage_items = require_perm("items.manage")

@router.get("", response_model=List[ItemOut])
def list_items(
    q: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = db.query(Item)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(func.lower(Item.name).like(like))
    if category:
        query = query.filter(Item.category == category)
    if active is not None:
        query = query.filter(Item.is_active == active)
    return query.order_by(Item.name.asc()).all()

@router.post("", response_model=ItemOut, status_code=201)
def create_item(payload: ItemCreate, db: Session = Depends(get_db), user: User = Depends(manage_items)):
    exists = db.query(Item).filter(func.lower(Item.name) == payload.name.lower()).first()
    if exists:
        raise HTTPException(409, "Item name already exists")
    code = generate_unique_item_code(db, payload.name)
    item = Item(
        name=payload.name,
        code=code,
        category=payload.category,
        stack_size=payload.stack_size,
        is_active=payload.is_active,
        created_by_user_id=user.id,
    )
    db.add(item); db.commit(); db.refresh(item)
    return item

@router.patch("/{item_id}", response_model=ItemOut)
def update_item(item_id: int, payload: ItemUpdate, db: Session = Depends(get_db), user: User = Depends(manage_items)):
    item = db.query(Item).get(item_id)
    if not item:
        raise HTTPException(404, "Item not found")

    if payload.name and payload.name.lower() != item.name.lower():
        conflict = db.query(Item).filter(func.lower(Item.name) == payload.name.lower()).first()
        if conflict:
            raise HTTPException(409, "Item name already exists")

    if payload.name is not None: item.name = payload.name
    if payload.category is not None: item.category = payload.category
    if payload.stack_size is not None: item.stack_size = payload.stack_size
    if payload.is_active is not None: item.is_active = payload.is_active

    db.commit(); db.refresh(item)
    return item
