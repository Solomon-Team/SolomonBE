# app/models/mc.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import (
    Integer, String, DateTime, Boolean, Float, UniqueConstraint, Index, ForeignKey, JSON
)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base

# Per-structure token allowing mod clients to POST events
class MCIngestToken(Base):
    __tablename__ = "mc_ingest_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    token_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)  # hex
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_mc_ingest_token_structure_active", "structure_id", "active"),
    )

# Latest snapshot per player UUID (per structure)
class MCLivePlayer(Base):
    __tablename__ = "mc_live_player"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)  # lowercased
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    z: Mapped[float] = mapped_column(Float, nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    hp_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    inventory_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    __table_args__ = (
        UniqueConstraint("structure_id", "uuid", name="uq_mc_live_player_struct_uuid"),
        Index("ix_mc_live_player_struct_user", "structure_id", "user_id"),
    )

# Lightweight position history (for trails/quick analytics)
class MCPositionHistory(Base):
    __tablename__ = "mc_position_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    z: Mapped[float] = mapped_column(Float, nullable=False)

    __table_args__ = (
        Index("ix_mc_position_history_struct_ts", "structure_id", "ts"),
        Index("ix_mc_position_history_struct_uuid_ts", "structure_id", "uuid", "ts"),
    )

# Optional snapshots you can enable later (kept simple)
class MCPlayerInventorySnapshot(Base):
    __tablename__ = "mc_player_inventory_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    uuid: Mapped[str] = mapped_column(String(64), nullable=False)
    inventory_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hp_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("structure_id", "uuid", name="uq_mc_player_inv_struct_uuid"),
    )

class MCContainerSnapshot(Base):
    __tablename__ = "mc_container_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    structure_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    x: Mapped[int] = mapped_column(Integer, nullable=False)
    y: Mapped[int] = mapped_column(Integer, nullable=False)
    z: Mapped[int] = mapped_column(Integer, nullable=False)
    items_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    signs_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    opened_by_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    opened_by_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("structure_id", "x", "y", "z", name="uq_mc_container_struct_xyz"),
    )
