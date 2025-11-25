# app/schemas/structures.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


class CreateJoinCodeRequest(BaseModel):
    expiresAt: Optional[datetime] = Field(None, description="Expiration date (null = never expires)")
    maxUses: Optional[int] = Field(None, ge=1, description="Max uses (null = unlimited)")


class JoinCodeOut(BaseModel):
    id: int
    code: str
    structureId: str
    expiresAt: Optional[datetime]
    maxUses: Optional[int]
    usedCount: int
    isActive: bool
    createdBy: Optional[str] = None  # username of creator
    createdAt: datetime

    class Config:
        from_attributes = True


class JoinCodeListResponse(BaseModel):
    codes: List[JoinCodeOut]


class JoinViaCodeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=16, description="Join code")


class JoinViaCodeResponse(BaseModel):
    success: bool
    structureId: str
    structureName: str


class LeaveStructureResponse(BaseModel):
    success: bool


class KickMemberResponse(BaseModel):
    success: bool


class StructureOut(BaseModel):
    id: str
    name: str
    displayName: str
    description: Optional[str] = None
    isActive: bool
    createdAt: datetime

    class Config:
        from_attributes = True


class PublicStructureOut(BaseModel):
    """Public structure info for the Nations list"""
    id: str
    displayName: str
    description: Optional[str] = None
    memberCount: int
    canJoin: bool  # False if user is already a member or guest

    class Config:
        from_attributes = True


class PublicStructuresResponse(BaseModel):
    structures: List[PublicStructureOut]


class DirectJoinRequest(BaseModel):
    """Request to join a structure directly (without code)"""
    pass  # No body needed, structure_id in URL


class DirectJoinResponse(BaseModel):
    success: bool
    structureId: str
    structureName: str
    message: str
