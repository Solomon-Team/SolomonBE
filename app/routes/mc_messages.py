# app/routes/mc_messages.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Dict
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.services import mc_policy
from app.services.deps import get_db, get_current_user
from app.models.user import User
from app.models.message import Message, MessageRecipientStatus
from app.schemas.message import MCMessage, MCAckIn

router = APIRouter(prefix="/mc", tags=["mc"])

@router.get("/messages", response_model=List[MCMessage])
def pull_messages(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    rows = (
        db.query(Message)
        .join(
            MessageRecipientStatus,
            and_(
                MessageRecipientStatus.message_id == Message.id,
                MessageRecipientStatus.user_id == current_user.id,
            ),
        )
        .filter(
            Message.structure_id == current_user.structure_id,
            MessageRecipientStatus.status.in_(["QUEUED", "FAILED"]),
            (Message.deliver_after.is_(None) | (Message.deliver_after <= now)),
            (Message.expires_at.is_(None) | (Message.expires_at > now)),
        )
        .order_by(Message.priority.desc(), Message.id.asc())
        .limit(100)
        .all()
    )

    # Resolve positions in batch (by kind) for this structure
    kinds: List[str] = list({r.kind for r in rows})
    kind_to_pos: Dict[str, str] = {}
    for k in kinds:
        kind_to_pos[k] = mc_policy.get_position(db, current_user.structure_id, k)

    return [
        MCMessage(
            id=r.id,
            text=r.text,
            kind=r.kind,
            meta=r.meta or {},
            expires_at=r.expires_at,
            priority=r.priority,
            created_at=r.created_at,
            position=kind_to_pos.get(r.kind, "LEFT"),
        )
        for r in rows
    ]

@router.post("/messages/ack")
def ack_messages(payload: MCAckIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    changed = 0
    now = datetime.now(timezone.utc)
    # delivered -> ACKED
    if payload.delivered:
        q = db.query(MessageRecipientStatus).filter(
            MessageRecipientStatus.user_id == current_user.id,
            MessageRecipientStatus.message_id.in_(payload.delivered),
        )
        for row in q.all():
            row.status = "ACKED"
            row.updated_at = now
            changed += 1
    # failed -> FAILED (+attempt_count)
    if payload.failed:
        q = db.query(MessageRecipientStatus).filter(
            MessageRecipientStatus.user_id == current_user.id,
            MessageRecipientStatus.message_id.in_(payload.failed),
        )
        for row in q.all():
            row.status = "FAILED"
            row.attempt_count = (row.attempt_count or 0) + 1
            row.updated_at = now
            changed += 1
    db.commit()
    return {"updated": changed}