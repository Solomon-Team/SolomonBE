from sqlalchemy import Column, Integer, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base

class LocationGuildMaster(Base):
    __tablename__ = "location_guild_masters"

    location_id = Column(Integer, ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    since = Column(DateTime, server_default=func.now(), nullable=False)

    location = relationship("Location", back_populates="guild_masters")
