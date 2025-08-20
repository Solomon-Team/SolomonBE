# app/models/party.py
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    UniqueConstraint
)
from sqlalchemy.sql import func
from app.core.database import Base

class Party(Base):
    __tablename__ = "parties"

    id = Column(Integer, primary_key=True)
    structure_id = Column(String(50), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    leader_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


    __table_args__ = (
        UniqueConstraint("structure_id", "name", name="uq_parties_struct_name"),
    )

class PartyMember(Base):
    __tablename__ = "party_members"

    party_id = Column(Integer, ForeignKey("parties.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
