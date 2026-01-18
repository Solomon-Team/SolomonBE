# app/schemas/mc.py
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional, List, Tuple
from pydantic import BaseModel, Field, field_validator

def _now() -> datetime:
    return datetime.now(timezone.utc)

class MCEventIn(BaseModel):
    # Accept both POC keys and normalized fields
    UUID: Optional[str] = None
    uuid: Optional[str] = None
    Username: Optional[str] = None
    username: Optional[str] = None
    XYZ_Cords: Optional[Tuple[float, float, float]] = None
    x: Optional[float] = None
    y: Optional[float] = None
    z: Optional[float] = None

    Event: Optional[str] = None
    event: Optional[str] = None

    HP: Optional[dict] = None
    Inventory: Optional[dict] = None
    Container: Optional[dict] = None
    Signs: Optional[list] = None

    ts: Optional[datetime] = None

    @field_validator("ts", mode="before")
    @classmethod
    def _parse_ts(cls, v):
        if v is None:
            return _now()
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except Exception:
                return _now()
        return v

    def normalized(self) -> "MCEventNorm":
        uid = (self.uuid or self.UUID or "").lower()
        name = self.username or self.Username or ""
        if self.XYZ_Cords:
            X, Y, Z = self.XYZ_Cords
        else:
            X = float(self.x if self.x is not None else 0.0)
            Y = float(self.y if self.y is not None else 0.0)
            Z = float(self.z if self.z is not None else 0.0)
        ev = (self.event or self.Event or "Position").strip()
        return MCEventNorm(
            uuid=uid, username=name, x=X, y=Y, z=Z, event=ev,
            ts=self.ts or _now(), hp=self.HP, inventory=self.Inventory,
            container=self.Container, signs=self.Signs
        )

class MCEventNorm(BaseModel):
    uuid: str
    username: str
    x: float
    y: float
    z: float
    event: str = "Position"
    ts: datetime
    hp: Optional[dict] = None
    inventory: Optional[dict] = None
    container: Optional[dict] = None
    signs: Optional[list] = None

class MCEventBatchIn(BaseModel):
    events: List[MCEventIn]

class MCPlayerSnapshotOut(BaseModel):
    uuid: str
    username: str
    x: float
    y: float
    z: float
    ts: datetime
    user_id: Optional[int] = None

class MCUuidsOut(BaseModel):
    players: dict[str, str]

class MCUuidDetailOut(BaseModel):
    uuid: str
    snapshot: dict

class MCItemsOut(BaseModel):
    players: dict
    chests: dict


# ChestSync Schemas
class ChestSnapshotOut(BaseModel):
    """Single chest snapshot for client consumption"""
    x: int
    y: int
    z: int
    items: Optional[dict] = None
    signs: Optional[list] = None
    opened_by: Optional[dict] = None
    last_seen_at: datetime

    @classmethod
    def from_model(cls, container) -> "ChestSnapshotOut":
        """Convert database model to schema"""
        return cls(
            x=container.x,
            y=container.y,
            z=container.z,
            items=container.items_json,
            signs=container.signs_json,
            opened_by={
                "uuid": container.opened_by_uuid,
                "username": container.opened_by_username
            } if container.opened_by_uuid else None,
            last_seen_at=container.last_seen_at
        )


class ChestSummaryStats(BaseModel):
    """Aggregate statistics for chest inventory"""
    total_chests: int
    last_updated_at: Optional[datetime] = None
    total_item_slots: int = 0


class ChestListOut(BaseModel):
    """Response for GET /mc/chests endpoint"""
    chests: List[ChestSnapshotOut]
    summary: ChestSummaryStats
