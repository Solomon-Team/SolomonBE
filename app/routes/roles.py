# app/routes/roles.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

import sqlalchemy as sa

from app.services.deps import get_db, get_current_user, get_current_structure, require_perm
from app.models.role import Role
from app.models.user import User
from app.schemas.role import RoleCreate, RoleUpdate, RoleOut

router = APIRouter(prefix="/roles", tags=["roles"])

# Only users with users.admin may manage roles
admin_guard = require_perm("users.admin")

@router.get("", response_model=list[RoleOut])
def list_roles(
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    _: User = Depends(admin_guard),
):
    rows = (
        db.query(Role)
        .filter(Role.structure_id == structure_id)
        .order_by(Role.name.asc())
        .all()
    )
    return rows

@router.post("", response_model=RoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreate,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    _: User = Depends(admin_guard),
):
    # Enforce per-structure uniqueness on name & code (case-insensitive)
    name_ci = func.lower(payload.name)
    code_ci = func.lower(payload.code)
    conflict = (
        db.query(Role)
        .filter(
            Role.structure_id == structure_id,
            (func.lower(Role.name) == name_ci) | (func.lower(Role.code) == code_ci),
        )
        .first()
    )
    if conflict:
        raise HTTPException(status_code=409, detail="Role with same name or code already exists")

    row = Role(
        structure_id=structure_id,
        name=payload.name,
        code=payload.code,
        permissions=payload.permissions or {},
        is_system=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.get("/{role_id}", response_model=RoleOut)
def get_role(
    role_id: int,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    _: User = Depends(admin_guard),
):
    row = db.query(Role).filter_by(id=role_id, structure_id=structure_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Role not found")
    return row

@router.patch("/{role_id}", response_model=RoleOut)
def update_role(
    role_id: int,
    payload: RoleUpdate,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    _: User = Depends(admin_guard),
):
    row = db.query(Role).filter_by(id=role_id, structure_id=structure_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Role not found")
    if row.is_system:
        # System roles may be editable if you wish; for now we lock name/code
        if payload.name or payload.code:
            raise HTTPException(400, detail="Cannot rename or recode a system role")

    if payload.name or payload.code:
        q = db.query(Role).filter(Role.structure_id == structure_id, Role.id != role_id)
        if payload.name:
            q = q.filter(func.lower(Role.name) == func.lower(payload.name))
        if payload.code:
            q = q.filter(func.lower(Role.code) == func.lower(payload.code))
        if q.first():
            raise HTTPException(409, "Duplicate role name/code in this structure")

    if payload.name is not None:
        row.name = payload.name
    if payload.code is not None:
        row.code = payload.code
    if payload.permissions is not None:
        row.permissions = payload.permissions

    db.commit(); db.refresh(row)
    return row

@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: int,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    _: object = Depends(admin_guard),
):
    # fetch role within current structure
    row = db.query(Role).filter_by(id=role_id, structure_id=structure_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Role not found")
    if row.is_system:
        raise HTTPException(status_code=400, detail="Cannot delete a system role")

    # guard: role assigned to any user via user_roles?
    assigned = db.execute(
        sa.text("SELECT 1 FROM user_roles WHERE role_id = :rid LIMIT 1"),
        {"rid": row.id},
    ).first()
    if assigned:
        raise HTTPException(status_code=400, detail="Cannot delete a role that is assigned to users")

    db.delete(row)
    db.commit()
    return