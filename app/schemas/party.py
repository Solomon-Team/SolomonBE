# app/schemas/party.py
from typing import List, Optional
from pydantic import BaseModel, Field

class PartyIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)

class PartyOut(PartyIn):
    id: int
    structure_id: str
    created_by_user_id: int
    class Config: from_attributes = True

class PartyListOut(BaseModel):
    id: int
    name: str
    members_count: int

class PartyMembersIn(BaseModel):
    user_ids: List[int]

class PartyLeaderIn(BaseModel):
    leader_user_id: Optional[int] = None


class PartyMemberView(BaseModel):
    user_id: int
    username: str
    minecraft_username: Optional[str] = None
    is_leader: bool

class PartyMeOut(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    leader_user_id: Optional[int] = None
    leader_username: Optional[str] = None
    leader_minecraft_username: Optional[str] = None
    members: List[PartyMemberView] = []


