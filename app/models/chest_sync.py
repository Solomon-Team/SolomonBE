# app/models/chest_sync.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Integer, String, DateTime, Float, UniqueConstraint, Index, ForeignKey, JSON
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base


class ChestSyncSnapshot(Base):
    """
    High-performance table for real-time chest inventory synchronization.

    Stores current state of all chests discovered by players.
    Optimized for fast reads with composite indexes.
    """
    __tablename__ = "chest_sync_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    z: Mapped[int] = mapped_column(Integer, nullable=False)
    world: Mapped[str | None] = mapped_column(String(64), nullable=True)
    items_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signs_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    opened_by_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_by_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (
        UniqueConstraint("structure_id", "x", "y", "z", name="uq_chest_sync_struct_xyz"),
        Index("ix_chest_sync_struct_last_seen", "structure_id", "last_seen_at"),
        Index("ix_chest_sync_struct_xyz", "structure_id", "x", "y", "z"),
    )


class ChestSyncHistory(Base):
    """
    Append-only history table for chest changes over time.

    Tracks historical chest states with TTL-based cleanup.
    Separate from current state to avoid slowing down real-time queries.
    """
    __tablename__ = "chest_sync_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    z: Mapped[int] = mapped_column(Integer, nullable=False)
    items_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signs_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    opened_by_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_by_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        Index("ix_chest_sync_history_struct_recorded", "structure_id", "recorded_at"),
        Index("ix_chest_sync_history_struct_xyz_recorded", "structure_id", "x", "y", "z", "recorded_at"),
    )
