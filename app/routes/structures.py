# app/routes/structures.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.services.deps import get_db, get_current_user
from app.models.user import User
from app.models.structure import Structure
from app.models.structure_join_code import StructureJoinCode
from app.schemas.structures import (
    CreateJoinCodeRequest,
    JoinCodeOut,
    JoinCodeListResponse,
    JoinViaCodeRequest,
    JoinViaCodeResponse,
    LeaveStructureResponse,
    KickMemberResponse,
    PublicStructureOut,
    PublicStructuresResponse,
    DirectJoinRequest,
    DirectJoinResponse
)
from app.core.security import generate_join_code
from app.services.audit import log_auth_event

router = APIRouter(prefix="/api/structures", tags=["structures"])


def has_structure_permission(user: User, structure_id: str, required_role: str = "ADMIN") -> bool:
    """
    Check if user has permission to manage a structure.
    Returns True if user is in the structure and has OWNER or ADMIN role.
    """
    if user.structure_id != structure_id:
        return False

    if not user.roles:
        return False

    # Check if user has required role or higher
    role_hierarchy = {"OWNER": 3, "ADMIN": 2, "MEMBER": 1}
    user_max_role = max([role_hierarchy.get(r.role_type, 0) for r in user.roles], default=0)
    required_level = role_hierarchy.get(required_role, 0)

    return user_max_role >= required_level


@router.post("/{structure_id}/codes", response_model=JoinCodeOut)
def create_join_code(
    structure_id: str,
    payload: CreateJoinCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate a join code for a structure (requires OWNER or ADMIN role).
    """
    # Check if structure exists
    structure = db.query(Structure).filter(Structure.id == structure_id).first()
    if not structure:
        raise HTTPException(status_code=404, detail="Structure not found")

    # Check permissions
    if not has_structure_permission(current_user, structure_id, "ADMIN"):
        raise HTTPException(
            status_code=403,
            detail="You must be an admin or owner of this structure to create join codes"
        )

    # Generate unique code
    code_str = generate_join_code(structure_id)

    # Ensure code is unique (very unlikely collision, but check anyway)
    existing = db.query(StructureJoinCode).filter(StructureJoinCode.code == code_str).first()
    if existing:
        # Regenerate if collision
        code_str = generate_join_code(structure_id) + str(datetime.now().microsecond)[:4]

    # Create join code
    join_code = StructureJoinCode(
        code=code_str,
        structure_id=structure_id,
        created_by_user_id=current_user.id,
        expires_at=payload.expiresAt,
        max_uses=payload.maxUses,
        used_count=0,
        is_active=True
    )

    db.add(join_code)

    # Log the event
    log_auth_event(
        db=db,
        event_type="join_code_created",
        user_id=current_user.id,
        mc_uuid=current_user.mc_uuid,
        request=request,
        metadata={"structure_id": structure_id, "code": code_str}
    )

    db.commit()
    db.refresh(join_code)

    return JoinCodeOut(
        id=join_code.id,
        code=join_code.code,
        structureId=join_code.structure_id,
        expiresAt=join_code.expires_at,
        maxUses=join_code.max_uses,
        usedCount=join_code.used_count,
        isActive=join_code.is_active,
        createdBy=current_user.username,
        createdAt=join_code.created_at
    )


@router.get("/{structure_id}/codes", response_model=JoinCodeListResponse)
def list_join_codes(
    structure_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all join codes for a structure (requires OWNER or ADMIN role).
    """
    # Check permissions
    if not has_structure_permission(current_user, structure_id, "ADMIN"):
        raise HTTPException(
            status_code=403,
            detail="You must be an admin or owner of this structure to view join codes"
        )

    # Get all codes for this structure
    codes = db.query(StructureJoinCode).filter(
        StructureJoinCode.structure_id == structure_id
    ).order_by(StructureJoinCode.created_at.desc()).all()

    # Build response
    code_outs = []
    for code in codes:
        created_by = db.query(User).filter(User.id == code.created_by_user_id).first()
        code_outs.append(JoinCodeOut(
            id=code.id,
            code=code.code,
            structureId=code.structure_id,
            expiresAt=code.expires_at,
            maxUses=code.max_uses,
            usedCount=code.used_count,
            isActive=code.is_active,
            createdBy=created_by.username if created_by else "Unknown",
            createdAt=code.created_at
        ))

    return JoinCodeListResponse(codes=code_outs)


@router.delete("/{structure_id}/codes/{code_id}", response_model=KickMemberResponse)
def revoke_join_code(
    structure_id: str,
    code_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Revoke a join code (soft delete - set is_active=False).
    Requires OWNER or ADMIN role.
    """
    # Check permissions
    if not has_structure_permission(current_user, structure_id, "ADMIN"):
        raise HTTPException(
            status_code=403,
            detail="You must be an admin or owner of this structure to revoke join codes"
        )

    # Find code
    code = db.query(StructureJoinCode).filter(
        StructureJoinCode.id == code_id,
        StructureJoinCode.structure_id == structure_id
    ).first()

    if not code:
        raise HTTPException(status_code=404, detail="Join code not found")

    # Revoke (soft delete)
    code.is_active = False

    # Log the event
    log_auth_event(
        db=db,
        event_type="join_code_revoked",
        user_id=current_user.id,
        mc_uuid=current_user.mc_uuid,
        request=request,
        metadata={"structure_id": structure_id, "code_id": code_id, "code": code.code}
    )

    db.commit()

    return KickMemberResponse(success=True)


@router.post("/join", response_model=JoinViaCodeResponse)
def join_via_code(
    payload: JoinViaCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Join a structure using a code (from website, requires JWT).
    """
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
    if current_user.structure_id:
        raise HTTPException(
            status_code=409,
            detail=f"You are already in structure '{current_user.structure_id}'. Please leave first."
        )

    # Get structure info
    structure = db.query(Structure).filter(Structure.id == code.structure_id).first()
    if not structure:
        raise HTTPException(status_code=500, detail="Structure not found")

    # Update user's structure
    current_user.structure_id = code.structure_id

    # Increment code usage
    code.used_count += 1

    # Log the event
    log_auth_event(
        db=db,
        event_type="structure_joined",
        user_id=current_user.id,
        mc_uuid=current_user.mc_uuid,
        request=request,
        metadata={"structure_id": code.structure_id, "code_id": code.id}
    )

    db.commit()

    return JoinViaCodeResponse(
        success=True,
        structureId=structure.id,
        structureName=structure.display_name
    )


@router.post("/leave", response_model=LeaveStructureResponse)
def leave_structure(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Leave current structure (removes all privileges and roles).
    """
    if not current_user.structure_id:
        raise HTTPException(status_code=400, detail="You are not in any structure")

    old_structure = current_user.structure_id

    # Clear structure membership
    current_user.structure_id = None
    current_user.membership_status = "unassigned"

    # Clear all roles
    current_user.roles.clear()

    # Log the event
    log_auth_event(
        db=db,
        event_type="structure_left",
        user_id=current_user.id,
        mc_uuid=current_user.mc_uuid,
        request=request,
        metadata={"old_structure_id": old_structure}
    )

    db.commit()

    return LeaveStructureResponse(success=True)


@router.delete("/{structure_id}/members/{user_id}", response_model=KickMemberResponse)
def kick_member(
    structure_id: str,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Kick a member from the structure (set their structure_id = NULL).
    Requires OWNER or ADMIN role.
    """
    # Check permissions
    if not has_structure_permission(current_user, structure_id, "ADMIN"):
        raise HTTPException(
            status_code=403,
            detail="You must be an admin or owner of this structure to kick members"
        )

    # Find target user
    target_user = db.query(User).filter(User.id == user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if target is in this structure
    if target_user.structure_id != structure_id:
        raise HTTPException(status_code=400, detail="User is not in this structure")

    # Prevent self-kick
    if target_user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot kick yourself. Use /leave instead.")

    # Remove from structure
    target_user.structure_id = None

    # Log the event
    log_auth_event(
        db=db,
        event_type="member_kicked",
        user_id=current_user.id,
        mc_uuid=current_user.mc_uuid,
        request=request,
        metadata={
            "structure_id": structure_id,
            "kicked_user_id": user_id,
            "kicked_mc_uuid": target_user.mc_uuid
        }
    )

    db.commit()

    return KickMemberResponse(success=True)


@router.get("/public", response_model=PublicStructuresResponse)
def get_public_structures(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all active structures (nations/factions) that can be joined.
    Shows member count and whether the current user can join.
    """
    # Get all active structures
    structures = db.query(Structure).filter(Structure.is_active == True).all()

    result = []
    for structure in structures:
        # Count members (exclude guests)
        member_count = db.query(User).filter(
            User.structure_id == structure.id,
            User.membership_status == "member"
        ).count()

        # User can join if they're not already in this structure or as a guest
        can_join = (
            current_user.structure_id != structure.id and
            current_user.membership_status != "guest"
        )

        result.append(PublicStructureOut(
            id=structure.id,
            displayName=structure.display_name,
            description=structure.description,
            memberCount=member_count,
            canJoin=can_join
        ))

    return PublicStructuresResponse(structures=result)


@router.post("/{structure_id}/request-join", response_model=DirectJoinResponse)
def request_join_structure(
    structure_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Request to join a structure directly (become a guest pending approval).
    Users cannot join if they're already in a structure or pending as a guest.
    """
    # Check if structure exists and is active
    structure = db.query(Structure).filter(
        Structure.id == structure_id,
        Structure.is_active == True
    ).first()

    if not structure:
        raise HTTPException(status_code=404, detail="Structure not found or not active")

    # Check if user is already in a structure
    if current_user.structure_id:
        if current_user.structure_id == structure_id:
            raise HTTPException(
                status_code=409,
                detail=f"You are already {'a member of' if current_user.membership_status == 'member' else 'pending approval for'} {structure.display_name}"
            )
        else:
            raise HTTPException(
                status_code=409,
                detail="You must leave your current nation before joining another"
            )

    # Check if user is a guest somewhere (shouldn't happen but safety check)
    if current_user.membership_status == "guest":
        raise HTTPException(
            status_code=409,
            detail="You already have a pending join request. Please wait for approval or leave first."
        )

    # Set user as guest of this structure
    current_user.structure_id = structure_id
    current_user.membership_status = "guest"

    # Log the event
    log_auth_event(
        db=db,
        event_type="structure_join_requested",
        user_id=current_user.id,
        mc_uuid=current_user.mc_uuid,
        request=request,
        metadata={"structure_id": structure_id, "method": "direct_join", "status": "guest"}
    )

    db.commit()

    return DirectJoinResponse(
        success=True,
        structureId=structure.id,
        structureName=structure.display_name,
        message=f"Join request sent to {structure.display_name}. An admin will review your request."
    )
