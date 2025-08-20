# app/routes/parties.py
from __future__ import annotations
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.user_profile import UserProfile
from app.models import Message, MessageTarget, MessageRecipientStatus
from app.schemas.message import PartyMessageCreate, MessageCreatedOut
from app.services.deps import get_db, require_perm, get_current_user
from app.models.user import User
from app.models.party import Party, PartyMember
from app.schemas.party import PartyIn, PartyOut, PartyListOut, PartyMembersIn, PartyLeaderIn, PartyMeOut, \
    PartyMemberView

router = APIRouter(prefix="/parties", tags=["parties"])
manage_parties = require_perm("users.admin")  # or "parties.manage" if you granted it



# ---------- NEW: user-facing endpoint ----------
@router.get("/me", response_model=List[PartyMeOut])
def my_parties(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Returns all parties the current user is a member of,
    including members' Minecraft usernames and the leader.
    """
    # Find parties where the caller is a member, scoped by structure
    parties: List[Party] = (
        db.query(Party)
        .join(PartyMember, PartyMember.party_id == Party.id)
        .filter(
            PartyMember.user_id == user.id,
            Party.structure_id == user.structure_id
        )
        .order_by(Party.name.asc())
        .all()
    )
    if not parties:
        return []

    party_ids = [p.id for p in parties]

    # Fetch all members for those parties in one query
    # NOTE: adjust 'User.minecraft_username' -> 'User.mc_username' if that's your column name.
    rows = (
        db.query(
            PartyMember.party_id,
            User.id.label("user_id"),
            User.username.label("username"),
            UserProfile.minecraft_username.label("minecraft_username"),  # <- from profile
        )
        .join(User, User.id == PartyMember.user_id)
        .outerjoin(UserProfile, UserProfile.user_id == User.id)  # <- left join profile
        .filter(PartyMember.party_id.in_(party_ids))
        .all()
    )

    # Build party_id -> members list
    members_map: dict[int, List[dict]] = {}
    for pid, uid, uname, mcu in rows:
        members_map.setdefault(pid, []).append(
            {"user_id": uid, "username": uname, "minecraft_username": mcu}
        )

    # Compose response
    out: List[PartyMeOut] = []
    for p in parties:
        members = []
        leader_username = None
        leader_mc = None

        for m in members_map.get(p.id, []):
            is_leader = p.leader_user_id is not None and m["user_id"] == p.leader_user_id
            if is_leader:
                leader_username = m["username"]
                leader_mc = m["minecraft_username"]
            members.append(
                PartyMemberView(
                    user_id=m["user_id"],
                    username=m["username"],
                    minecraft_username=m["minecraft_username"],
                    is_leader=is_leader,
                )
            )

        out.append(
            PartyMeOut(
                id=p.id,
                name=p.name,
                description=p.description,
                leader_user_id=p.leader_user_id,
                leader_username=leader_username,
                leader_minecraft_username=leader_mc,
                members=members,
            )
        )

    return out

@router.get("", response_model=List[PartyListOut])
def list_parties(db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    rows = (
        db.query(Party.id, Party.name, func.count(PartyMember.user_id).label("members_count"))
        .outerjoin(PartyMember, PartyMember.party_id == Party.id)
        .filter(Party.structure_id == user.structure_id)
        .group_by(Party.id)
        .order_by(Party.name.asc())
        .all()
    )
    return [{"id": r.id, "name": r.name, "members_count": r.members_count} for r in rows]

@router.post("", response_model=PartyOut, status_code=201)
def create_party(payload: PartyIn, db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    dup = db.query(Party).filter(
        Party.structure_id == user.structure_id, func.lower(Party.name) == func.lower(payload.name)
    ).first()
    if dup:
        raise HTTPException(status_code=409, detail="Party with this name already exists")
    row = Party(
        structure_id=user.structure_id,
        name=payload.name,
        description=payload.description,
        created_by_user_id=user.id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row

@router.get("/{party_id}", response_model=PartyOut)
def get_party(party_id: int, db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    row = db.query(Party).filter(Party.id == party_id, Party.structure_id == user.structure_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row

@router.put("/{party_id}", response_model=PartyOut)
def update_party(party_id: int, payload: PartyIn, db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    row = db.query(Party).filter(Party.id == party_id, Party.structure_id == user.structure_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    exists = db.query(Party).filter(
        Party.structure_id == user.structure_id, func.lower(Party.name) == func.lower(payload.name), Party.id != party_id
    ).first()
    if exists:
        raise HTTPException(status_code=409, detail="Another party with this name exists")
    row.name = payload.name
    row.description = payload.description
    db.commit()
    db.refresh(row)
    return row

@router.delete("/{party_id}", status_code=204)
def delete_party(party_id: int, db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    row = db.query(Party).filter(Party.id == party_id, Party.structure_id == user.structure_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return

@router.get("/{party_id}/members", response_model=List[int])
def get_party_members(party_id: int, db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    exists = db.query(Party.id).filter(Party.id == party_id, Party.structure_id == user.structure_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Not found")
    rows = db.query(PartyMember.user_id).filter(PartyMember.party_id == party_id).order_by(PartyMember.user_id.asc()).all()
    return [r.user_id for r in rows]

@router.put("/{party_id}/members", response_model=List[int])
def set_party_members(party_id: int, payload: PartyMembersIn, db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    party = db.query(Party).filter(Party.id == party_id, Party.structure_id == user.structure_id).first()
    if not party:
        raise HTTPException(status_code=404, detail="Not found")

    # Validate all users belong to same structure
    ids = list(set(payload.user_ids))
    if len(ids) > 0:
        cnt = db.query(User).filter(User.id.in_(ids), User.structure_id == user.structure_id).count()
        if cnt != len(ids):
            raise HTTPException(status_code=400, detail="Some users do not belong to this structure")

    # Replace membership
    db.query(PartyMember).filter(PartyMember.party_id == party_id).delete(synchronize_session=False)
    for uid in ids:
        db.add(PartyMember(party_id=party_id, user_id=uid))

    if party.leader_user_id is not None and party.leader_user_id not in ids:
        party.leader_user_id = None

    db.commit()
    rows = db.query(PartyMember.user_id).filter(PartyMember.party_id == party_id).order_by(PartyMember.user_id.asc()).all()
    return [r.user_id for r in rows]

@router.put("/{party_id}/leader", response_model=PartyOut)
def set_party_leader(party_id: int, payload: PartyLeaderIn, db: Session = Depends(get_db), user: User = Depends(manage_parties)):
    party = db.query(Party).filter(Party.id == party_id, Party.structure_id == user.structure_id).first()
    if not party:
        raise HTTPException(status_code=404, detail="Not found")

    leader_id: Optional[int] = payload.leader_user_id
    if leader_id is None:
        party.leader_user_id = None
        db.commit()
        db.refresh(party)
        return party

    # Validate leader is a user of same structure
    has_user = db.query(User.id).filter(User.id == leader_id, User.structure_id == user.structure_id).first()
    if not has_user:
        raise HTTPException(status_code=400, detail="Leader user not in this structure")

    # Ensure leader is a member (auto-add if missing)
    is_member = db.query(PartyMember).filter(PartyMember.party_id == party_id, PartyMember.user_id == leader_id).first()
    if not is_member:
        db.add(PartyMember(party_id=party_id, user_id=leader_id))
    party.leader_user_id = leader_id

    db.commit()
    db.refresh(party)
    return party


@router.post("/{party_id}/messages", response_model=MessageCreatedOut, status_code=201)
def send_message_to_party(
    party_id: int,
    payload: PartyMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(manage_parties),
):
    party = db.query(Party).filter(Party.id == party_id, Party.structure_id == user.structure_id).first()
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")

    msg = Message(
        structure_id=user.structure_id,
        text=payload.text,
        kind=payload.kind,
        meta=payload.meta or None,
        deliver_after=payload.deliver_after,
        expires_at=payload.expires_at,
        requires_ack=payload.requires_ack,
        priority=payload.priority,
        created_by_user_id=user.id,
    )
    db.add(msg)
    db.flush()

    # target the party
    db.add(MessageTarget(message_id=msg.id, party_id=party_id))

    # expand recipients (all members now)
    member_rows = db.query(PartyMember.user_id).filter(PartyMember.party_id == party_id).all()
    member_ids = [r.user_id for r in member_rows]
    for uid in member_ids:
        exists = db.query(MessageRecipientStatus).filter(
            MessageRecipientStatus.message_id == msg.id,
            MessageRecipientStatus.user_id == uid,
        ).first()
        if not exists:
            db.add(MessageRecipientStatus(message_id=msg.id, user_id=uid, status="QUEUED"))

    db.commit()
    return {"message_id": msg.id, "recipients": len(member_ids)}