# app/models/message.py
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey,
    UniqueConstraint, CheckConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.core.database import Base

class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    structure_id = Column(String(50), nullable=False, index=True)
    text = Column(Text, nullable=False)
    kind = Column(String(24), nullable=False, server_default="CHAT")  # CHAT|TITLE|ACTIONBAR|BOSSBAR
    meta = Column(JSONB, nullable=True)
    deliver_after = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    requires_ack = Column(Boolean, nullable=False, server_default="false")
    priority = Column(String(16), nullable=False, server_default="NORMAL")
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class MessageTarget(Base):
    __tablename__ = "message_targets"

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    party_id = Column(Integer, ForeignKey("parties.id", ondelete="CASCADE"), nullable=True)

    __table_args__ = (
        CheckConstraint("(user_id IS NOT NULL) <> (party_id IS NOT NULL)", name="ck_message_targets_xor"),
        UniqueConstraint("message_id", "user_id", name="uq_message_targets_msg_user"),
        UniqueConstraint("message_id", "party_id", name="uq_message_targets_msg_party"),
    )

class MessageRecipientStatus(Base):
    __tablename__ = "message_recipient_status"

    message_id = Column(Integer, ForeignKey("messages.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    status = Column(String(16), nullable=False, server_default="QUEUED")  # QUEUED|FAILED|ACKED
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    attempt_count = Column(Integer, nullable=False, server_default="0")

    __table_args__ = (
        Index("ix_mrs_user_status", "user_id", "status"),
        Index("ix_mrs_msg_status", "message_id", "status"),
    )
