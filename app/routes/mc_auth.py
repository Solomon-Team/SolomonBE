# app/routes/mc_auth.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
import os

from app.services.deps import get_db
from app.models.user import User
from app.models.structure import Structure
from app.models.magic_login_token import MagicLoginToken
from app.models.structure_join_code import StructureJoinCode
from app.schemas.mc_auth import (
    MagicLinkRequest,
    MagicLinkResponse,
    MCJoinStructureRequest,
    MCJoinStructureResponse
)
from app.core.security import generate_magic_token
from app.services.audit import log_auth_event

router = APIRouter(prefix="/api/mc", tags=["mc-auth"])

# Get frontend URL from env or use default
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
MAGIC_LINK_EXPIRY_MINUTES = int(os.getenv("MAGIC_LINK_EXPIRY_MINUTES", "5"))


@router.post("/magic-link", response_model=MagicLinkResponse)
def request_magic_link(
    payload: MagicLinkRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Request a magic login link for a Minecraft player.
    Creates user if first time, generates short-lived token.
    """
    # Find or create user by MC UUID
    user = db.query(User).filter(User.mc_uuid == payload.mcUuid).first()
    is_new_user = False

    if not user:
        # Create new user (no structure yet)
        user = User(
            mc_uuid=payload.mcUuid,
            username=payload.mcName,
            has_password=False
        )
        db.add(user)
        db.flush()
        is_new_user = True
    else:
        # Update username if MC name changed (username should match MC name)
        if user.username != payload.mcName:
            user.username = payload.mcName
            db.flush()

    # Generate magic token
    token = generate_magic_token()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRY_MINUTES)

    magic_token = MagicLoginToken(
        token=token,
        user_id=user.id,
        mc_uuid=payload.mcUuid,
        expires_at=expires_at,
        ip_address=request.client.host if request.client else None
    )
    db.add(magic_token)

    # Log the event
    log_auth_event(
        db=db,
        event_type="magic_link_request",
        user_id=user.id,
        mc_uuid=payload.mcUuid,
        request=request,
        metadata={"is_new_user": is_new_user}
    )

    db.commit()

    # Build magic URL (no hash - Vue uses history mode)
    magic_url = f"{FRONTEND_URL}/magic-login/{token}"

    return MagicLinkResponse(
        token=token,
        magicUrl=magic_url,
        expiresAt=expires_at,
        isNewUser=is_new_user
    )


@router.post("/join-structure", response_model=MCJoinStructureResponse)
def join_structure_mc(
    payload: MCJoinStructureRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Join a structure using a join code (from Minecraft).
    Validates code and updates user's structure_id.
    """
    # Find user by MC UUID
    user = db.query(User).filter(User.mc_uuid == payload.mcUuid).first()
    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found. Please login first to create an account."
        )

    # Find and validate join code
    code = db.query(StructureJoinCode).filter(
        StructureJoinCode.code == payload.code,
        StructureJoinCode.is_active == True
    ).first()

    if not code:
        raise HTTPException(status_code=400, detail="Invalid or inactive join code")

    # Check expiration
    if code.expires_at and code.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Join code has expired")

    # Check max uses
    if code.max_uses and code.used_count >= code.max_uses:
        raise HTTPException(status_code=400, detail="Join code has reached maximum uses")

    # Check if user is already in a structure
    if user.structure_id:
        raise HTTPException(
            status_code=409,
            detail=f"You are already in structure '{user.structure_id}'. Please leave first."
        )

    # Get structure info
    structure = db.query(Structure).filter(Structure.id == code.structure_id).first()
    if not structure:
        raise HTTPException(status_code=500, detail="Structure not found")

    # Update user's structure and set as guest (pending approval)
    user.structure_id = code.structure_id
    user.membership_status = "guest"

    # Increment code usage
    code.used_count += 1

    # Log the event
    log_auth_event(
        db=db,
        event_type="structure_join_requested",
        user_id=user.id,
        mc_uuid=payload.mcUuid,
        request=request,
        metadata={"structure_id": code.structure_id, "code_id": code.id, "status": "guest"}
    )

    db.commit()

    return MCJoinStructureResponse(
        success=True,
        structureId=structure.id,
        structureName=structure.display_name,
        message=f"Join request sent to {structure.display_name}. An admin will approve your request."
    )
