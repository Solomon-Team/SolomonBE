# app/models/schematic.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Integer, String, DateTime, Boolean, LargeBinary, ForeignKey, JSON, Index, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Schematic(Base):
    """
    Stores schematic files uploaded by users.

    For files < 10MB, data is stored inline in schematic_data.
    For larger files, use external storage and store path in storage_path.
    """
    __tablename__ = "schematics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), ForeignKey("structures.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # File metadata
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)

    # Storage: either inline or external
    schematic_data: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # For files < 10MB
    storage_path: Mapped[str | None] = mapped_column(String(512), nullable=True)  # For large files

    # Ownership and timestamps
    uploaded_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Visibility
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    split_results: Mapped[list["SchematicSplitResult"]] = relationship(
        "SchematicSplitResult",
        back_populates="schematic",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_schematic_struct_name", "structure_id", "name"),
        Index("ix_schematic_struct_uploaded", "structure_id", "uploaded_at"),
        Index("ix_schematic_hash", "file_hash"),
    )


class SchematicSplitResult(Base):
    """
    Stores KD-Tree split results for a schematic.

    Each record represents one leaf (chunk) from the split operation,
    containing bounds, metrics, and material counts.
    """
    __tablename__ = "schematic_split_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schematic_id: Mapped[int] = mapped_column(Integer, ForeignKey("schematics.id", ondelete="CASCADE"), nullable=False)

    # Leaf identification
    leaf_index: Mapped[int] = mapped_column(Integer, nullable=False)
    region_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Bounding box
    bounds_min_x: Mapped[int] = mapped_column(Integer, nullable=False)
    bounds_min_y: Mapped[int] = mapped_column(Integer, nullable=False)
    bounds_min_z: Mapped[int] = mapped_column(Integer, nullable=False)
    bounds_max_x: Mapped[int] = mapped_column(Integer, nullable=False)
    bounds_max_y: Mapped[int] = mapped_column(Integer, nullable=False)
    bounds_max_z: Mapped[int] = mapped_column(Integer, nullable=False)

    # Metrics
    blocks_non_air: Mapped[int] = mapped_column(Integer, nullable=False)
    stacks_needed: Mapped[int] = mapped_column(Integer, nullable=False)

    # Material counts as JSON: {"minecraft:stone": 123, "minecraft:oak_planks": 456, ...}
    material_counts: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    # Relationships
    schematic: Mapped["Schematic"] = relationship("Schematic", back_populates="split_results")

    __table_args__ = (
        Index("ix_split_result_schematic", "schematic_id"),
        Index("ix_split_result_schematic_leaf", "schematic_id", "leaf_index"),
    )
