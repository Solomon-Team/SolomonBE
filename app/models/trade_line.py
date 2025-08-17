
from sqlalchemy import (
    Column, Integer, BigInteger, String, ForeignKey, CheckConstraint, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime
from app.core.database import Base

class TradeLine(Base):
    __tablename__ = "trade_lines"

    id = Column(Integer, primary_key=True, index=True)
    trade_id = Column(Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="RESTRICT"), nullable=False)

    # Label only; math is driven solely by from->to parties
    direction = Column(String(24), nullable=False)  # e.g., GAINED|GIVEN etc.

    quantity = Column(BigInteger, nullable=False)

    # Existing location parties (kept for back-compat & location-only lines)
    from_location_id = Column(Integer, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True)
    to_location_id   = Column(Integer, ForeignKey("locations.id", ondelete="RESTRICT"), nullable=True)

    # NEW: user parties (exactly one of user/location per side must be set)
    from_user_id = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    to_user_id   = Column(Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

    # NEW: per-structure movement reason (validate in service layer by trade.structure_id)
    movement_reason_code = Column(String(48), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # Relationships (lightweight; keep names consistent with your codebase)
    trade = relationship("Trade", back_populates="lines")
    item = relationship("Item")
    from_location = relationship("Location", foreign_keys=[from_location_id])
    to_location = relationship("Location", foreign_keys=[to_location_id])
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

    # XOR checks: exactly one party kind per side (user XOR location)
    __table_args__ = (
        CheckConstraint("(from_user_id IS NULL) <> (from_location_id IS NULL)", name="ck_trade_lines_from_party_xor"),
        CheckConstraint("(to_user_id IS NULL) <> (to_location_id IS NULL)", name="ck_trade_lines_to_party_xor"),
        Index("ix_trade_lines_reason_code", movement_reason_code),
        Index("ix_trade_lines_item_trade", trade_id, item_id),
    )