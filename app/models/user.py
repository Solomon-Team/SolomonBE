from sqlalchemy import Column, Integer, String, ForeignKeyConstraint, Table, ForeignKey
from sqlalchemy.orm import relationship
from app.core.database import Base


user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    structure_id = Column(String(50), nullable=False)

    roles = relationship("Role", secondary=user_roles, back_populates="users", lazy="joined")

    trades = relationship("Trade", back_populates="user")
