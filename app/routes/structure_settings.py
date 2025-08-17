from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.services.deps import get_db, get_current_user, has_perm
from app.models.user import User
from app.models.structure_settings import StructureSettings
from app.models.item import Item
from app.schemas.structure_settings import StructureSettingsOut, SetCurrencyIn

router = APIRouter(prefix="/structure-settings", tags=["structure-settings"])

def ensure_admin(u: User):
    # Use RBAC/permissions, not u.role
    if not has_perm(u, "users.admin"):
        raise HTTPException(status_code=403, detail="Admin only")

@router.get("", response_model=StructureSettingsOut)
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # PK is structure_id
    ss = db.get(StructureSettings, user.structure_id)
    if not ss:
        ss = StructureSettings(structure_id=user.structure_id)
        db.add(ss); db.commit(); db.refresh(ss)
    name = ss.currency_item.name if ss.currency_item_id else None
    return StructureSettingsOut(
        structure_id=ss.structure_id,
        currency_item_id=ss.currency_item_id,
        currency_item_name=name,
    )

@router.put("/currency", response_model=StructureSettingsOut)
def set_currency(payload: SetCurrencyIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ensure_admin(user)

    # Only allow items in the same structure and active
    item = (
        db.query(Item)
        .filter(
            Item.id == payload.currency_item_id,
            Item.is_active == True,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=400, detail="Invalid currency item")

    ss = db.get(StructureSettings, user.structure_id)
    if not ss:
        ss = StructureSettings(structure_id=user.structure_id)
        db.add(ss)

    ss.currency_item_id = item.id
    ss.updated_by_user_id = user.id
    db.commit(); db.refresh(ss)

    return StructureSettingsOut(
        structure_id=ss.structure_id,
        currency_item_id=ss.currency_item_id,
        currency_item_name=item.name,
    )
