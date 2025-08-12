from sqlalchemy import Column, Integer, String, Boolean, DateTime, func, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.core.database import Base

class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    structure_id = Column(String(50), nullable=False)  # tenant scope

    name = Column(String(80), nullable=False)          # e.g. "Admin"
    code = Column(String(80), nullable=False)          # e.g. "ADMIN"
    permissions = Column(JSONB, nullable=False,
                         server_default=text("'{}'::jsonb"))
    is_system = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    users = relationship("User", secondary="user_roles", back_populates="roles")

    __table_args__ = (
        UniqueConstraint("structure_id", "name", name="uq_roles_structure_name"),
        UniqueConstraint("structure_id", "code", name="uq_roles_structure_code"),
    )
