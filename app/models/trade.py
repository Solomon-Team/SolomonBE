from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import relationship

from app.core.database import Base


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    structure_id = Column(String(50), nullable=False, index=True)
    from_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    to_location_id = Column(Integer, ForeignKey("locations.id"), nullable=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    user = relationship("User", back_populates="trades")
    lines = relationship(
        "TradeLine",
        back_populates="trade",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Trade id={self.id} structure={self.structure_id} user={self.user_id} ts={self.timestamp}>"
