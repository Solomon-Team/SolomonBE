# app/routes/players.py
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_
from datetime import datetime, timezone

from app.services.deps import get_db, get_current_user, has_perm
from app.models.user import User
from app.models.role import Role
from app.models.structure import Structure
from app.schemas.players import (
    UnassignedPlayersResponse,
    PlayerOut,
    AssignPlayerRequest,
    AssignPlayerResponse,
    GuestsResponse,
    GuestOut,
    ApproveGuestRequest,
    ApproveGuestResponse,
    RejectGuestResponse
)
from app.services.audit import log_auth_event

router = APIRouter(prefix="/api", tags=["players"])


def get_lowest_member_role(db: Session, structure_id: str) -> Role:
    """Get the lowest non-guest role for a structure (typically MEMBER)."""
    # Try to find MEMBER role first
    member_role = db.query(Role).filter(
        Role.structure_id == structure_id,
        Role.role_type == "MEMBER"
    ).first()

    if member_role:
        return member_role

    # If no MEMBER role, find any non-OWNER, non-ADMIN role
    fallback_role = db.query(Role).filter(
        Role.structure_id == structure_id,
        Role.role_type.notin_(["OWNER", "ADMIN"])
    ).first()

    if fallback_role:
        return fallback_role

    # Last resort: find any role
    any_role = db.query(Role).filter(
        Role.structure_id == structure_id
    ).first()

    if not any_role:
        raise HTTPException(status_code=500, detail="No roles found for structure")

    return any_role


@router.get("/admin/unassigned-players", response_model=UnassignedPlayersResponse)
def get_unassigned_players(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all players who have no structure assigned.
    Requires: users.view_unassigned permission (configurable per structure).

    For now, accessible to all admins of any structure.
    """
    # Check if user is an admin of their structure
    if not current_user.structure_id:
        raise HTTPException(status_code=403, detail="You must be in a structure to access this")

    # Check if user has admin permissions
    is_admin = any(role.role_type in ["OWNER", "ADMIN"] for role in current_user.roles)

    # TODO: Make this configurable - check for users.view_unassigned permission
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You need admin permissions to view unassigned players"
        )

    # Query unassigned players
    unassigned = db.query(User).filter(
        or_(
            User.structure_id.is_(None),
            User.membership_status == "unassigned"
        )
    ).order_by(User.created_at.desc()).all()

    return UnassignedPlayersResponse(
        players=[
            PlayerOut(
                userId=u.id,
                mcUuid=u.mc_uuid,
                username=u.username,
                hasPassword=u.has_password,
                structureId=u.structure_id,
                membershipStatus=u.membership_status,
                createdAt=u.created_at,
                lastLogin=u.last_login
            ) for u in unassigned
        ],
        count=len(unassigned)
    )


@router.post("/admin/assign-player/{user_id}", response_model=AssignPlayerResponse)
def assign_player_to_structure(
    user_id: int,
    payload: AssignPlayerRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Assign an unassigned player to the admin's structure.
    Gives them the lowest member role by default, or a specified role.
    Requires: users.assign permission (for now, admin only).
    """
    # Check if current user is admin
    if not current_user.structure_id:
        raise HTTPException(status_code=403, detail="You must be in a structure")

    is_admin = any(role.role_type in ["OWNER", "ADMIN"] for role in current_user.roles)

    # TODO: Make configurable with users.assign permission
    if not is_admin:
        raise HTTPException(status_code=403, detail="You need admin permissions to assign players")

    # Find the player to assign
    player = db.query(User).filter(User.id == user_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    # Verify player is unassigned
    if player.structure_id is not None:
        raise HTTPException(
            status_code=400,
            detail=f"Player is already in structure '{player.structure_id}'"
        )

    # Get the structure
    structure = db.query(Structure).filter(Structure.id == current_user.structure_id).first()
    if not structure:
        raise HTTPException(status_code=500, detail="Your structure not found")

    # Determine which role to assign
    if payload.roleId:
        # Verify role exists and belongs to this structure
        role = db.query(Role).filter(
            Role.id == payload.roleId,
            Role.structure_id == current_user.structure_id
        ).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found in your structure")
    else:
        # Get lowest member role
        role = get_lowest_member_role(db, current_user.structure_id)

    # Assign player to structure
    player.structure_id = current_user.structure_id
    player.membership_status = "member"

    # Assign role
    if role not in player.roles:
        player.roles.append(role)

    # Log the event
    log_auth_event(
        db=db,
        event_type="player_assigned",
        user_id=player.id,
        mc_uuid=player.mc_uuid,
        request=request,
        metadata={
            "assigned_by": current_user.id,
            "structure_id": current_user.structure_id,
            "role_id": role.id,
            "role_type": role.role_type
        }
    )

    db.commit()

    return AssignPlayerResponse(
        success=True,
        userId=player.id,
        structureId=structure.id,
        structureName=structure.display_name,
        membershipStatus="member",
        roleAssigned=role.role_type
    )


@router.get("/structures/{structure_id}/guests", response_model=GuestsResponse)
def get_structure_guests(
    structure_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all guests (pending members) for a structure.
    Requires: members.approve_guests permission (for now, admin only).
    """
    # Check if user is in the structure
    if current_user.structure_id != structure_id:
        raise HTTPException(status_code=403, detail="You are not in this structure")

    # Check if user is admin
    is_admin = any(role.role_type in ["OWNER", "ADMIN"] for role in current_user.roles)

    # TODO: Make configurable with members.approve_guests permission
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You need admin permissions to view pending guests"
        )

    # Query guests for this structure
    guests = db.query(User).filter(
        User.structure_id == structure_id,
        User.membership_status == "guest"
    ).order_by(User.created_at.desc()).all()

    return GuestsResponse(
        guests=[
            GuestOut(
                userId=g.id,
                mcUuid=g.mc_uuid,
                username=g.username,
                createdAt=g.created_at,
                lastLogin=g.last_login
            ) for g in guests
        ],
        count=len(guests)
    )


@router.post("/structures/{structure_id}/approve-guest/{user_id}", response_model=ApproveGuestResponse)
def approve_guest(
    structure_id: str,
    user_id: int,
    payload: ApproveGuestRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Approve a guest, making them a full member with a role.
    Requires: members.approve_guests permission (for now, admin only).
    """
    # Check if user is in the structure
    if current_user.structure_id != structure_id:
        raise HTTPException(status_code=403, detail="You are not in this structure")

    # Check if user is admin
    is_admin = any(role.role_type in ["OWNER", "ADMIN"] for role in current_user.roles)

    # TODO: Make configurable with members.approve_guests permission
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You need admin permissions to approve guests"
        )

    # Find the guest
    guest = db.query(User).filter(User.id == user_id).first()
    if not guest:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify guest is in this structure and has guest status
    if guest.structure_id != structure_id:
        raise HTTPException(status_code=400, detail="User is not in this structure")

    if guest.membership_status != "guest":
        raise HTTPException(
            status_code=400,
            detail=f"User is not a guest (current status: {guest.membership_status})"
        )

    # Determine which role to assign
    if payload.roleId:
        # Verify role exists and belongs to this structure
        role = db.query(Role).filter(
            Role.id == payload.roleId,
            Role.structure_id == structure_id
        ).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found in this structure")
    else:
        # Get lowest member role
        role = get_lowest_member_role(db, structure_id)

    # Approve guest
    guest.membership_status = "member"

    # Assign role
    if role not in guest.roles:
        guest.roles.append(role)

    # Log the event
    log_auth_event(
        db=db,
        event_type="guest_approved",
        user_id=guest.id,
        mc_uuid=guest.mc_uuid,
        request=request,
        metadata={
            "approved_by": current_user.id,
            "structure_id": structure_id,
            "role_id": role.id,
            "role_type": role.role_type
        }
    )

    db.commit()

    return ApproveGuestResponse(
        success=True,
        userId=guest.id,
        membershipStatus="member",
        roleAssigned=role.role_type
    )


@router.post("/structures/{structure_id}/reject-guest/{user_id}", response_model=RejectGuestResponse)
def reject_guest(
    structure_id: str,
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reject a guest, removing them from the structure.
    Requires: members.approve_guests permission (for now, admin only).
    """
    # Check if user is in the structure
    if current_user.structure_id != structure_id:
        raise HTTPException(status_code=403, detail="You are not in this structure")

    # Check if user is admin
    is_admin = any(role.role_type in ["OWNER", "ADMIN"] for role in current_user.roles)

    # TODO: Make configurable with members.approve_guests permission
    if not is_admin:
        raise HTTPException(
            status_code=403,
            detail="You need admin permissions to reject guests"
        )

    # Find the guest
    guest = db.query(User).filter(User.id == user_id).first()
    if not guest:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify guest is in this structure and has guest status
    if guest.structure_id != structure_id:
        raise HTTPException(status_code=400, detail="User is not in this structure")

    if guest.membership_status != "guest":
        raise HTTPException(
            status_code=400,
            detail=f"User is not a guest (current status: {guest.membership_status})"
        )

    # Reject guest - remove from structure
    guest.structure_id = None
    guest.membership_status = "unassigned"

    # Remove any roles they might have
    guest.roles.clear()

    # Log the event
    log_auth_event(
        db=db,
        event_type="guest_rejected",
        user_id=guest.id,
        mc_uuid=guest.mc_uuid,
        request=request,
        metadata={
            "rejected_by": current_user.id,
            "structure_id": structure_id
        }
    )

    db.commit()

    return RejectGuestResponse(
        success=True,
        userId=guest.id,
        message=f"Guest {guest.username} has been rejected and removed from the structure"
    )
