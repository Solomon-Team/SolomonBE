# app/schemas/mc_trades.py
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal

Flow = Literal["FROM", "TO"]

class MCItemIn(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    amount: int = Field(gt=0)

    @field_validator("name", "code")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

class MCChest(BaseModel):
    x: int
    y: int
    z: int

class MCTradeIn(BaseModel):
    player_mc_username: str = Field(alias="player_mc_username")
    direction: Flow                      # "FROM" | "TO"
    chest: MCChest
    items: List[MCItemIn]

    class Config:
        populate_by_name = True
