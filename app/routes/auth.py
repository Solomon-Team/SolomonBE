from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from app.schemas.user import UserLogin
from app.models.user import User
from app.core.security import verify_password, create_jwt_token
from app.services.deps import get_db

router = APIRouter()

@router.post("/auth/login")
def login(form: UserLogin, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.username == form.username)
        .first()
    )
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Invalid credentials")

    role_codes = [r.code for r in user.roles]
    role_ids   = [r.id for r in user.roles]
    # merge permissions: any True wins
    merged_perms = {}
    for r in user.roles:
        if r.permissions:
            for k, v in r.permissions.items():
                if v:
                    merged_perms[k] = True

    token = create_jwt_token({
        "sub": str(user.id),
        "username": user.username,
        "structure_id": user.structure_id,
        "role_ids": role_ids,
        "role_codes": role_codes,
        "permissions": merged_perms,
    })
    return {
        "access_token": token,
        "token_type": "bearer",
        "role_codes": role_codes,
        "permissions": merged_perms,
        "structure_id": user.structure_id,
        "user_id": user.id,
        "username": user.username,
    }
