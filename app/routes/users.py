# app/routes/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from app.services.deps import get_db, get_current_user, get_current_structure, require_perm
from app.models.user import User
from app.models.role import Role
from app.schemas.user import UserCreate, UserOut, UserUpdateRoles
from app.core.security import hash_password

router = APIRouter(prefix="/users", tags=["users"])
admin_guard = require_perm("users.admin")

def _role_in_structure(db: Session, structure_id: str, role_id: int) -> Role | None:
    return db.query(Role).filter_by(id=role_id, structure_id=structure_id).first()

def _to_user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        username=u.username,
        structure_id=u.structure_id,
        role_ids=[r.id for r in u.roles],
        role_codes=[r.code for r in u.roles],
        role_names=[r.name for r in u.roles],
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db),
                current_user: User = Depends(admin_guard),
                structure_id: str = Depends(get_current_structure)):
    if db.query(User.id).filter(User.username == payload.username).first():
        raise HTTPException(409, "Username already exists")

    roles = (
        db.query(Role)
        .filter(Role.structure_id == structure_id, Role.id.in_(payload.role_ids))
        .all()
    )
    if len(roles) != len(set(payload.role_ids)):
        raise HTTPException(400, "One or more role_ids invalid for this structure")

    new_user = User(
        username=payload.username,
        hashed_password=hash_password(payload.password),
        structure_id=structure_id,
    )
    new_user.roles = roles
    db.add(new_user);
    db.commit();
    db.refresh(new_user)

    return UserOut(
        id=new_user.id,
        username=new_user.username,
        structure_id=new_user.structure_id,
        role_ids=[r.id for r in new_user.roles],
        role_codes=[r.code for r in new_user.roles],
        role_names=[r.name for r in new_user.roles],
    )

@router.get("", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db),
               current_user: User = Depends(admin_guard),
               structure_id: str = Depends(get_current_structure)):
    users = (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.structure_id == structure_id)
        .order_by(User.username.asc())
        .all()
    )
    return [
        UserOut(
            id=u.id,
            username=u.username,
            structure_id=u.structure_id,
            role_ids=[r.id for r in u.roles],
            role_codes=[r.code for r in u.roles],
            role_names=[r.name for r in u.roles],
        ) for u in users
    ]


@router.patch("/{user_id}/roles", response_model=UserOut)
def replace_user_roles(user_id: int, payload: UserUpdateRoles,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(admin_guard),
                       structure_id: str = Depends(get_current_structure)):
    u = db.query(User).filter_by(id=user_id, structure_id=structure_id).first()
    if not u:
        raise HTTPException(404, "User not found")
    roles = (
        db.query(Role)
        .filter(Role.structure_id == structure_id, Role.id.in_(payload.role_ids))
        .all()
    )
    if len(roles) != len(set(payload.role_ids)):
        raise HTTPException(400, "One or more role_ids invalid for this structure")
    u.roles = roles
    db.commit();
    db.refresh(u)
    return _to_user_out(u)
