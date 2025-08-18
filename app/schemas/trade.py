from pydantic import BaseModel, field_validator
from typing import List, Optional, Literal
from datetime import datetime

Direction = Literal["GAINED", "GIVEN"]


class TradeLineIn(BaseModel):
    item_id: int
    direction: Direction
    quantity: int
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    from_user_id: Optional[int] = None
    to_user_id: Optional[int] = None
    movement_reason_code: Optional[str] = None  # e.g. MINED / TRANSFERRED

    @field_validator("from_user_id")
    @classmethod
    def _noop(cls, v): return v  # keep lints happy

    @field_validator("to_user_id")
    @classmethod
    def _noop2(cls, v): return v

    @field_validator("movement_reason_code")
    @classmethod
    def _noop3(cls, v): return v

    # XOR checks at schema level (friendlier than DB error)
    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        m = super().model_validate(obj, *args, **kwargs)
        if (m.from_user_id is None) == (m.from_location_id is None):
            raise ValueError("Exactly one of from_user_id or from_location_id is required")
        if (m.to_user_id is None) == (m.to_location_id is None):
            raise ValueError("Exactly one of to_user_id or to_location_id is required")
        return m

class TradeLineOut(BaseModel):
    id: int
    item_id: int
    quantity: int
    direction: Direction
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    from_user_id: Optional[int] = None
    to_user_id: Optional[int] = None
    movement_reason_code: Optional[str] = None


class TradeCreate(BaseModel):
    timestamp: datetime
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    lines: List[TradeLineIn]

class TradeOut(BaseModel):
    id: int
    timestamp: datetime
    from_location_id: Optional[int]
    to_location_id: Optional[int]
    user_id: int
    username: str
    gained: List[TradeLineOut]
    given: List[TradeLineOut]
    profit: Optional[float] = None

class TradeItem(BaseModel):
    name: str
    quantity: int

class TradeLogCreate(BaseModel):
    items_given: List[TradeItem]
    items_gained: List[TradeItem]
    from_location: str
    to_location: str

class TradeLogOut(BaseModel):
    id: int
    timestamp: str
    items_given: List[TradeItem]
    items_gained: List[TradeItem]
    from_location: str
    to_location: str
    actor_user_id: int
    actor_username: Optional[str] = ""

    # NEW:
    profit: Optional[float] = None              # string per Decimal->JSON
    currency_item_name: Optional[str] = None  # es. "Iron Ingot"
    unpriced: bool = False                    # true se mancano valutazioni

    class Config:
        from_attributes = True
