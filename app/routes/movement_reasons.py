from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.core.database import SessionLocal
from app.services.deps import get_current_user, require_perm
from app.models.user import User
from app.models.movement_reason import MovementReason
from app.schemas.movement_reason import MovementReasonIn, MovementReasonOut

router = APIRouter(prefix="/movement-reasons", tags=["movement-reasons"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/", response_model=List[MovementReasonOut])
def list_reasons(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    q = db.query(MovementReason).filter(MovementReason.structure_id == current.structure_id)
    if active_only:
        q = q.filter(MovementReason.is_active == True)  # noqa: E712
    rows = q.order_by(MovementReason.code.asc()).all()
    return [
        MovementReasonOut(
            structure_id=r.structure_id,
            code=r.code,
            name=r.name,
            is_active=r.is_active,
        ) for r in rows
    ]

@router.post("/", response_model=MovementReasonOut, dependencies=[Depends(require_perm("movement_reasons.manage"))])
def create_reason(
    body: MovementReasonIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    exists = (
        db.query(MovementReason)
        .filter(MovementReason.structure_id == current.structure_id, MovementReason.code == body.code)
        .first()
    )
    if exists:
        raise HTTPException(status_code=409, detail="Reason code already exists")

    row = MovementReason(
        structure_id=current.structure_id,
        code=body.code,
        name=body.name,
        is_active=body.is_active,
    )
    db.add(row); db.commit(); db.refresh(row)
    return MovementReasonOut(structure_id=row.structure_id, code=row.code, name=row.name, is_active=row.is_active)

@router.patch("/{code}", response_model=MovementReasonOut, dependencies=[Depends(require_perm("movement_reasons.manage"))])
def update_reason(
    code: str,
    body: MovementReasonIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    row = (
        db.query(MovementReason)
        .filter(MovementReason.structure_id == current.structure_id, MovementReason.code == code)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Reason not found")

    # If code changes, check uniqueness
    if body.code != code:
        dup = (
            db.query(MovementReason)
            .filter(MovementReason.structure_id == current.structure_id, MovementReason.code == body.code)
            .first()
        )
        if dup:
            raise HTTPException(status_code=409, detail="Reason code already exists")
        row.code = body.code

    row.name = body.name
    row.is_active = body.is_active
    db.commit(); db.refresh(row)
    return MovementReasonOut(structure_id=row.structure_id, code=row.code, name=row.name, is_active=row.is_active)
