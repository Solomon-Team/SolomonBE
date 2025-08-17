from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.services.deps import get_current_user, require_perm
from app.models.user import User
from app.models.user_profile import UserProfile
from app.schemas.user_profile import UserProfileIn, UserProfileOut

router = APIRouter(prefix="/users", tags=["users"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/{user_id}/profile", response_model=UserProfileOut)
def get_profile(user_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    # Scope check: same structure
    target = db.query(User).filter(User.id == user_id).first()
    if not target or target.structure_id != current.structure_id:
        raise HTTPException(status_code=404, detail="User not found")
    prof = db.query(UserProfile).get(user_id)
    if not prof:
        prof = UserProfile(user_id=user_id)
        db.add(prof); db.commit(); db.refresh(prof)
    return UserProfileOut(user_id=user_id, discord_username=prof.discord_username, minecraft_username=prof.minecraft_username, notes=prof.notes)

@router.put("/{user_id}/profile", response_model=UserProfileOut)
def upsert_profile(
    user_id: int,
    body: UserProfileIn,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    # Permissions: self can edit self; admins can edit anyone
    if current.id != user_id:
        # admin-level permission
        require_perm("users.profile.manage")(current)

    target = db.query(User).filter(User.id == user_id).first()
    if not target or target.structure_id != current.structure_id:
        raise HTTPException(status_code=404, detail="User not found")

    prof = db.query(UserProfile).get(user_id)
    if not prof:
        prof = UserProfile(user_id=user_id)
        db.add(prof)

    prof.discord_username = body.discord_username
    prof.minecraft_username = body.minecraft_username
    prof.notes = body.notes
    db.commit(); db.refresh(prof)
    return UserProfileOut(user_id=user_id, discord_username=prof.discord_username, minecraft_username=prof.minecraft_username, notes=prof.notes)
