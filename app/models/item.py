from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, func, LargeBinary
from sqlalchemy.orm import relationship
from app.core.database import Base

class Item(Base):
    __tablename__ = "items"

    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    code = Column(String(60), nullable=False, unique=True)
    category = Column(String(50), nullable=False)
    stack_size = Column(Integer, nullable=False, default=64)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    icon_image = Column(LargeBinary, nullable=True)
    icon_mime_type = Column(String(64), nullable=True)
    icon_updated_at = Column(DateTime(timezone=True), nullable=True, server_default=None)

    creator = relationship("User")
