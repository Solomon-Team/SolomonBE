# app/models/message_position_policy.py
from sqlalchemy import Column, Integer, String, DateTime, Index
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import ENUM
from app.core.database import Base

# Keep in sync with Alembic enum name
MC_POSITION = ENUM('TOP', 'LEFT', 'RIGHT', 'BOTTOM', name='mc_position', create_type=False)

class MessagePositionPolicy(Base):
    __tablename__ = "message_position_policy"

    id = Column(Integer, primary_key=True)
    structure_id = Column(String(50), nullable=True, index=True)  # NULL => global default
    kind = Column(String(24), nullable=False)
    position = Column(MC_POSITION, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

# Partial unique constraints are created in Alembic via partial unique indexes
Index('uq_mpp_struct_kind', MessagePositionPolicy.structure_id, MessagePositionPolicy.kind, unique=True, postgresql_where=None)  # placeholder for IDEs
