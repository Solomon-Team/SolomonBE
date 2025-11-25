# app/schemas/players.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class PlayerOut(BaseModel):
    """Player information for lists"""
    userId: int
    mcUuid: str
    username: str
    hasPassword: bool
    structureId: Optional[str] = None
    membershipStatus: str
    createdAt: datetime
    lastLogin: Optional[datetime] = None

    class Config:
        from_attributes = True


class UnassignedPlayersResponse(BaseModel):
    """Response for unassigned players list"""
    players: List[PlayerOut]
    count: int


class AssignPlayerRequest(BaseModel):
    """Request to assign a player to a structure"""
    roleId: Optional[int] = Field(None, description="Role to assign (optional, defaults to lowest role)")


class AssignPlayerResponse(BaseModel):
    """Response after assigning a player"""
    success: bool
    userId: int
    structureId: str
    structureName: str
    membershipStatus: str
    roleAssigned: str


class GuestOut(BaseModel):
    """Guest player information"""
    userId: int
    mcUuid: str
    username: str
    createdAt: datetime
    lastLogin: Optional[datetime] = None

    class Config:
        from_attributes = True


class GuestsResponse(BaseModel):
    """Response for guests list"""
    guests: List[GuestOut]
    count: int


class ApproveGuestRequest(BaseModel):
    """Request to approve a guest"""
    roleId: Optional[int] = Field(None, description="Role to assign (optional, defaults to lowest role)")


class ApproveGuestResponse(BaseModel):
    """Response after approving a guest"""
    success: bool
    userId: int
    membershipStatus: str
    roleAssigned: str


class RejectGuestResponse(BaseModel):
    """Response after rejecting a guest"""
    success: bool
    userId: int
    message: str
