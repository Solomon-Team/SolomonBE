# app/routes/auth_mc.py
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select

from app.services.deps import get_db
from app.models.user import User
from app.models.user_profile import UserProfile
from app.core.security import verify_password, create_jwt_token

router = APIRouter(prefix="/auth/mc", tags=["auth"])

class MCLoginRequest(BaseModel):
    username: str
    password: str
    minecraft_username: str | None = None  # optional; overwrite profile if provided

@router.post("/login")
def mc_login(payload: MCLoginRequest, db: Session = Depends(get_db)):
    """
    Minecraft-friendly login:
    - Authenticates exactly like /auth/login (same JWT content & perms).
    - If minecraft_username is provided, updates the caller's profile with that value.
    """
    # 1) Authenticate (same logic as /auth/login)
    user: User | None = (
        db.query(User)
        .options(joinedload(User.roles))
        .filter(User.username == payload.username)
        .first()
    )
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # 2) Overwrite caller's minecraft_username if provided
    if payload.minecraft_username is not None:
        prof = db.execute(
            select(UserProfile).where(UserProfile.user_id == user.id)
        ).scalar_one_or_none()
        if prof:
            prof.minecraft_username = payload.minecraft_username
        else:
            prof = UserProfile(user_id=user.id, minecraft_username=payload.minecraft_username)
            db.add(prof)
        db.flush()  # ensure persistence before we return

    # 3) Build claims identically to /auth/login
    role_codes = [r.code for r in user.roles]
    role_ids   = [r.id for r in user.roles]
    merged_perms: dict[str, bool] = {}
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

    db.commit()
    # 4) Return the same shape your website login returns
    return {
        "access_token": token,
        "token_type": "bearer",
        "role_codes": role_codes,
        "permissions": merged_perms,
        "structure_id": user.structure_id,
        "user_id": user.id,
        "username": user.username,
    }
