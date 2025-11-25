from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship
from app.core.database import Base


class StructureJoinCode(Base):
    __tablename__ = "structure_join_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), unique=True, nullable=False, index=True)
    structure_id = Column(String(50), ForeignKey("structures.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # NULL = never expires
    max_uses = Column(Integer, nullable=True)  # NULL = unlimited
    used_count = Column(Integer, nullable=False, server_default="0")
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships
    structure = relationship("Structure", foreign_keys=[structure_id])
    created_by = relationship("User", foreign_keys=[created_by_user_id])
