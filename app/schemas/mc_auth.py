# app/schemas/mc_auth.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class MagicLinkRequest(BaseModel):
    mcUuid: str = Field(..., min_length=36, max_length=36, description="Minecraft UUID")
    mcName: str = Field(..., min_length=1, max_length=16, description="Minecraft username")


class MagicLinkResponse(BaseModel):
    token: str
    magicUrl: str
    expiresAt: datetime
    isNewUser: bool

    class Config:
        from_attributes = True


class MCJoinStructureRequest(BaseModel):
    mcUuid: str = Field(..., min_length=36, max_length=36, description="Minecraft UUID")
    code: str = Field(..., min_length=1, max_length=16, description="Join code")


class MCJoinStructureResponse(BaseModel):
    success: bool
    structureId: str
    structureName: str
    message: str
