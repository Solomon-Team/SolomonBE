from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Table, func
from sqlalchemy.orm import relationship
from app.core.database import Base


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("assigned_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    mc_uuid = Column(String(36), unique=True, nullable=False, index=True)  # Primary identifier from Minecraft
    username = Column(String(50), unique=True, nullable=False, index=True)  # Minecraft username (cannot be changed)
    hashed_password = Column(String(255), nullable=True)  # Password (optional)
    has_password = Column(Boolean, nullable=False, server_default="false")
    structure_id = Column(String(50), ForeignKey("structures.id", ondelete="SET NULL"), nullable=True)
    membership_status = Column(String(20), nullable=False, server_default="unassigned")  # unassigned, guest, member
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    roles = relationship("Role", secondary=user_roles, back_populates="users", lazy="joined")
    trades = relationship("Trade", back_populates="user")
    structure = relationship("Structure", foreign_keys=[structure_id])
