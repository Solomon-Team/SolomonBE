from pydantic import BaseModel
from typing import Optional, List, Literal

LocationType = Literal["TOWN","OUTPOST","MINE","PORT","OTHER"]

class LocationCreate(BaseModel):
    name: str
    type: LocationType = "OTHER"
    description: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    z: Optional[int] = None
    is_active: bool = True

class LocationOut(BaseModel):
    id: int
    structure_id: str
    name: str
    code: str
    type: LocationType
    description: Optional[str]
    x: Optional[int]
    y: Optional[int]
    z: Optional[int]
    is_active: bool
    class Config: from_attributes = True

class GuildMasterAssign(BaseModel):
    user_ids: List[int]
