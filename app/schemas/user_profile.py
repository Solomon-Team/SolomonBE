from typing import Optional
from pydantic import BaseModel, Field

class UserProfileIn(BaseModel):
    discord_username: Optional[str] = Field(None, max_length=64)
    minecraft_username: Optional[str] = Field(None, max_length=64)
    notes: Optional[str] = Field(None, max_length=1024)

class UserProfileOut(UserProfileIn):
    user_id: int
