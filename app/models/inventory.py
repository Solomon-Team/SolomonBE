# app/models/inventory.py
from sqlalchemy import (
    Column, Integer, BigInteger, String, DateTime, ForeignKey,
    PrimaryKeyConstraint, Index
)
from sqlalchemy.sql import func
from app.core.database import Base

class PlayerInventory(Base):
    __tablename__ = "player_inventory"

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    structure_id = Column(String(16), nullable=False)

    quantity = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "item_id", "structure_id", name="pk_player_inventory"),
        Index("ix_player_inventory_user_item", "user_id", "item_id"),
    )


class PlayerInventoryLedger(Base):
    __tablename__ = "player_inventory_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)
    structure_id = Column(String(16), nullable=False)
    delta_qty = Column(BigInteger, nullable=False)  # negative if user is 'from', positive if 'to'

    trade_id = Column(Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    trade_line_id = Column(Integer, ForeignKey("trade_lines.id", ondelete="CASCADE"), nullable=False)
    movement_reason_code = Column(String(48), nullable=True)

    timestamp = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_pil_user_item_time", "user_id", "item_id", "timestamp"),
        Index("ix_pil_struct_time", "structure_id", "timestamp"),
    )
