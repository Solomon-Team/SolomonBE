from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime

Direction = Literal["GAINED", "GIVEN"]


class TradeLineIn(BaseModel):
    item_id: int
    direction: Direction
    quantity: int
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None

class TradeLineOut(TradeLineIn):
    id: int


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
