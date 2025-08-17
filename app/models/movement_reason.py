# app/models/movement_reason.py
from sqlalchemy import Column, Integer, String, Boolean, UniqueConstraint, Index
from app.core.database import Base

class MovementReason(Base):
    __tablename__ = "movement_reasons"

    id = Column(Integer, primary_key=True)
    structure_id = Column(String(16), nullable=False)
    code = Column(String(48), nullable=False)
    name = Column(String(128), nullable=False)          
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("structure_id", "code", name="uq_movement_reason_struct_code"),
        Index("ix_movement_reasons_struct_active", structure_id, is_active),
    )
