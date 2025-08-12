from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

LocationType = ("TOWN", "OUTPOST", "MINE", "PORT", "OTHER")

class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    structure_id = Column(String(50), nullable=False)
    name = Column(String(120), nullable=False)
    code = Column(String(32), nullable=False)
    type = Column(Enum(*LocationType, name="locationtype"), nullable=False, default="OTHER")
    description = Column(Text)
    x = Column(Integer)
    y = Column(Integer)
    z = Column(Integer)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)   # <—
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)  # <—

    guild_masters = relationship("LocationGuildMaster", back_populates="location", cascade="all, delete-orphan")
