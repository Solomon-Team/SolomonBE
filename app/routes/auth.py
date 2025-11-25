# app/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.services.deps import get_db, get_current_user
from app.models.user import User
from app.models.magic_login_token import MagicLoginToken
from app.schemas.auth import (
    MagicLoginRequest,
    MagicLoginResponse,
    SetPasswordRequest,
    SetPasswordResponse,
    LoginRequest,
    LoginResponse,
    UserInfo
)
from app.core.security import (
    verify_password,
    hash_password,
    create_jwt_token,
    validate_password_strength
)
from app.services.audit import log_auth_event

router = APIRouter(prefix="/api/auth", tags=["auth"])


def build_user_info(user: User) -> UserInfo:
    """Helper to build UserInfo from User model."""
    return UserInfo(
        userId=user.id,
        mcUuid=user.mc_uuid,
        username=user.username,
        hasPassword=user.has_password,
        structureId=user.structure_id,
        membershipStatus=user.membership_status,
        roles=[r.role_type for r in user.roles] if user.roles else []
    )


def build_jwt_for_user(user: User) -> str:
    """Helper to build JWT token for user."""
    return create_jwt_token({
        "sub": str(user.id),
        "mcUuid": user.mc_uuid,
        "username": user.username,
        "hasPassword": user.has_password,
        "structureId": user.structure_id,
        "membershipStatus": user.membership_status,
        "roleIds": [r.id for r in user.roles] if user.roles else [],
        "roleCodes": [r.role_type for r in user.roles] if user.roles else []
    })


@router.post("/magic-login", response_model=MagicLoginResponse)
def magic_login(
    payload: MagicLoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Exchange magic token for JWT.
    Validates token (not expired, not used), marks as used, returns JWT.
    """
    # Find token
    token_record = db.query(MagicLoginToken).filter(
        MagicLoginToken.token == payload.token
    ).first()

    if not token_record:
        log_auth_event(
            db=db,
            event_type="magic_login_failed",
            request=request,
            metadata={"reason": "token_not_found"}
        )
        db.commit()
        raise HTTPException(status_code=404, detail="Token not found")

    # Check if expired
    if token_record.expires_at < datetime.now(timezone.utc):
        log_auth_event(
            db=db,
            event_type="magic_login_failed",
            user_id=token_record.user_id,
            mc_uuid=token_record.mc_uuid,
            request=request,
            metadata={"reason": "token_expired"}
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Token has expired")

    # Check if already used
    if token_record.used_at:
        log_auth_event(
            db=db,
            event_type="magic_login_failed",
            user_id=token_record.user_id,
            mc_uuid=token_record.mc_uuid,
            request=request,
            metadata={"reason": "token_already_used"}
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Token has already been used")

    # Mark token as used
    token_record.used_at = datetime.now(timezone.utc)

    # Load user with roles
    user = db.query(User).filter(User.id == token_record.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update last login
    user.last_login = datetime.now(timezone.utc)

    # Log successful login
    log_auth_event(
        db=db,
        event_type="magic_login",
        user_id=user.id,
        mc_uuid=user.mc_uuid,
        request=request
    )

    db.commit()

    # Generate JWT
    jwt_token = build_jwt_for_user(user)

    return MagicLoginResponse(
        access_token=jwt_token,
        token_type="bearer",
        user=build_user_info(user)
    )


@router.post("/set-password", response_model=SetPasswordResponse)
def set_password(
    payload: SetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Set password for web login (requires JWT).
    Validates password strength. Username is already set from Minecraft.
    """
    # Validate password strength
    is_valid, error_msg = validate_password_strength(payload.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Update user password
    current_user.hashed_password = hash_password(payload.password)
    current_user.has_password = True

    # Log the event
    log_auth_event(
        db=db,
        event_type="password_set",
        user_id=current_user.id,
        mc_uuid=current_user.mc_uuid,
        request=request,
        metadata={"username": current_user.username}
    )

    db.commit()

    return SetPasswordResponse(
        success=True,
        username=current_user.username
    )


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Standard username/password login.
    Returns JWT on success.
    """
    # Find user by username
    user = db.query(User).filter(User.username == payload.username).first()

    if not user or not user.hashed_password or not verify_password(payload.password, user.hashed_password):
        # Log failed attempt
        log_auth_event(
            db=db,
            event_type="login_failed",
            request=request,
            metadata={"username": payload.username, "reason": "invalid_credentials"}
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Update last login
    user.last_login = datetime.now(timezone.utc)

    # Log successful login
    log_auth_event(
        db=db,
        event_type="login_success",
        user_id=user.id,
        mc_uuid=user.mc_uuid,
        request=request,
        metadata={"username": payload.username}
    )

    db.commit()

    # Generate JWT
    jwt_token = build_jwt_for_user(user)

    return LoginResponse(
        access_token=jwt_token,
        token_type="bearer",
        user=build_user_info(user)
    )
