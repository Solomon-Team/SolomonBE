from sqlalchemy import Column, Integer, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base
LineDirection = ("GAINED", "GIVEN")

class TradeLine(Base):
    __tablename__ = "trade_lines"

    id = Column(Integer, primary_key=True)
    trade_id = Column(Integer, ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(Integer, ForeignKey("items.id"), nullable=False)
    direction = Column(Enum(*LineDirection, name="linedirection"), nullable=False)
    quantity = Column(Integer, nullable=False)
    from_location_id = Column(Integer, ForeignKey("locations.id"))
    to_location_id = Column(Integer, ForeignKey("locations.id"))

    trade = relationship("Trade", back_populates="lines")
