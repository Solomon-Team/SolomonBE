from sqlalchemy import Column, BigInteger, Integer, String, DateTime, Text, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class AuthAuditLog(Base):
    __tablename__ = "auth_audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String(50), nullable=False, index=True)  # magic_link_request, magic_login, password_set, login_success, login_failed
    mc_uuid = Column(String(36), nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    event_metadata = Column("metadata", JSONB, nullable=True)  # Map to 'metadata' column in DB
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)

    # Relationship
    user = relationship("User", foreign_keys=[user_id])
