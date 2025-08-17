from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, Enum, Index, and_
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

LocationType = ("TOWN", "OUTPOST", "MINE", "PORT", "OTHER")
ExternalKind = ("IMPORT", "EXPORT")  # NEW



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

    is_external = Column(Boolean, nullable=False, default=False)
    external_kind = Column(Enum(*ExternalKind, name="external_kind"), nullable=True)

    guild_masters = relationship("LocationGuildMaster", back_populates="location", cascade="all, delete-orphan")


Index(
    "uq_locations_import_per_structure",
    Location.structure_id,
    unique=True,
    postgresql_where=and_(Location.is_external.is_(True), Location.external_kind == "IMPORT"),
)

Index(
    "uq_locations_export_per_structure",
    Location.structure_id,
    unique=True,
    postgresql_where=and_(Location.is_external.is_(True), Location.external_kind == "EXPORT"),
)