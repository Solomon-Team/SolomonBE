# app/routes/messages.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from sqlalchemy import func, select, Integer, cast

from app.services.deps import get_db, require_perm, get_current_user
from app.models.user import User
from app.models.party import Party, PartyMember
from app.models.message import Message, MessageTarget, MessageRecipientStatus
from app.schemas.message import MessageCreate, MessageCreatedOut, MessageOutboxRow, PartyMessageCreate

router = APIRouter(prefix="/messages", tags=["messages"])

send_perm = require_perm("users.admin")
view_perm  = require_perm("users.admin")

@router.post("/broadcast", response_model=MessageCreatedOut, status_code=201)
def broadcast_to_structure(
    payload: PartyMessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(send_perm),   # admin-only, reuse same gate as /outbox
):
    """
    Broadcast a message to ALL users in the caller's structure.
    Admin-only. Reuses the same queue mechanism as /messages/outbox.
    """
    # Create the message header (identical to /outbox, minus explicit targets)
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
    db.flush()  # get msg.id

    # Resolve recipients: every user in the same structure (including the sender)
    recipient_ids = [r.id for r in db.query(User.id).filter(User.structure_id == user.structure_id).all()]
    unique_ids = set(recipient_ids)

    # For each recipient: add a MessageTarget (user) and queue delivery status
    for uid in unique_ids:
        # targets (nice to have; keeps parity with /outbox per-user targeting)
        db.add(MessageTarget(message_id=msg.id, user_id=uid))
        # queue
        exists = db.query(MessageRecipientStatus).filter(
            MessageRecipientStatus.message_id == msg.id,
            MessageRecipientStatus.user_id == uid,
        ).first()
        if not exists:
            db.add(MessageRecipientStatus(message_id=msg.id, user_id=uid, status="QUEUED"))

    db.commit()
    return {"message_id": msg.id, "recipients": len(unique_ids)}


@router.post("/outbox", response_model=MessageCreatedOut, status_code=201)
def send_message(payload: MessageCreate, db: Session = Depends(get_db), user: User = Depends(send_perm)):
    # validate party ids & user ids belong to same structure
    if payload.to_party_ids:
        part_cnt = db.query(Party).filter(Party.id.in_(payload.to_party_ids), Party.structure_id == user.structure_id).count()
        if part_cnt != len(set(payload.to_party_ids)):
            raise HTTPException(status_code=400, detail="Some parties do not belong to this structure")
    if payload.to_user_ids:
        usr_cnt = db.query(User).filter(User.id.in_(payload.to_user_ids), User.structure_id == user.structure_id).count()
        if usr_cnt != len(set(payload.to_user_ids)):
            raise HTTPException(status_code=400, detail="Some users do not belong to this structure")

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
    db.flush()  # get msg.id

    # targets
    for pid in set(payload.to_party_ids or []):
        db.add(MessageTarget(message_id=msg.id, party_id=pid))
    for uid in set(payload.to_user_ids or []):
        db.add(MessageTarget(message_id=msg.id, user_id=uid))

    # expand recipients -> MessageRecipientStatus
    recipient_user_ids: set[int] = set(payload.to_user_ids or [])
    if payload.to_party_ids:
        rows = (
            db.query(PartyMember.user_id)
            .join(Party, Party.id == PartyMember.party_id)
            .filter(Party.id.in_(payload.to_party_ids), Party.structure_id == user.structure_id)
            .all()
        )
        recipient_user_ids.update([r.user_id for r in rows])

    for uid in recipient_user_ids:
        exists = db.query(MessageRecipientStatus).filter(
            MessageRecipientStatus.message_id == msg.id,
            MessageRecipientStatus.user_id == uid,
        ).first()
        if not exists:
            db.add(MessageRecipientStatus(message_id=msg.id, user_id=uid, status="QUEUED"))

    db.commit()
    return {"message_id": msg.id, "recipients": len(recipient_user_ids)}

@router.get("/outbox", response_model=List[MessageOutboxRow])
def list_outbox(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(view_perm),
):
    rows = (
        db.query(
            Message.id,
            Message.text,
            Message.kind,
            Message.created_at,
            Message.deliver_after,
            Message.expires_at,
            func.count(MessageRecipientStatus.user_id).label("total"),
            func.sum(cast(MessageRecipientStatus.status == "QUEUED", Integer)).label("queued"),
            func.sum(cast(MessageRecipientStatus.status == "FAILED", Integer)).label("failed"),
            func.sum(cast(MessageRecipientStatus.status == "ACKED", Integer)).label("acked"),
        )
        .outerjoin(MessageRecipientStatus, MessageRecipientStatus.message_id == Message.id)
        .filter(Message.structure_id == user.structure_id)
        .group_by(Message.id)
        .order_by(Message.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "text": r.text,
            "kind": r.kind,
            "created_at": r.created_at,
            "deliver_after": r.deliver_after,
            "expires_at": r.expires_at,
            "total": int(r.total or 0),
            "queued": int(r.queued or 0),
            "failed": int(r.failed or 0),
            "acked": int(r.acked or 0),
        }
        for r in rows
    ]
