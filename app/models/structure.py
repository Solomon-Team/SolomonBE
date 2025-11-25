from sqlalchemy import Column, String, Boolean, DateTime, Text, func
from app.core.database import Base


class Structure(Base):
    __tablename__ = "structures"

    id = Column(String(50), primary_key=True)
    name = Column(String(120), nullable=False)
    display_name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
