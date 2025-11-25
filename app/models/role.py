from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, func, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    structure_id = Column(String(50), ForeignKey("structures.id", ondelete="CASCADE"), nullable=False, index=True)
    role_type = Column(String(20), nullable=False)  # OWNER, ADMIN, MEMBER, CUSTOM
    name = Column(String(80), nullable=False)
    permissions = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    is_custom = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    users = relationship("User", secondary="user_roles", back_populates="roles")
    structure = relationship("Structure", foreign_keys=[structure_id])

    __table_args__ = (
        UniqueConstraint("structure_id", "role_type", "name", name="uq_roles_structure_type_name"),
    )
