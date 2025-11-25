# app/schemas/auth.py
from pydantic import BaseModel, Field, constr
from typing import Optional, List


class MagicLoginRequest(BaseModel):
    token: str = Field(..., min_length=1, description="Magic login token")


class UserInfo(BaseModel):
    userId: int
    mcUuid: str
    username: str  # Minecraft username, used for login
    hasPassword: bool
    structureId: Optional[str] = None
    membershipStatus: str = "unassigned"  # unassigned, guest, member
    roles: List[str] = []

    class Config:
        from_attributes = True


class MagicLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo


class SetPasswordRequest(BaseModel):
    password: constr(min_length=8, max_length=128) = Field(..., description="Password (min 8 chars)")


class SetPasswordResponse(BaseModel):
    success: bool
    username: str


class LoginRequest(BaseModel):
    username: str = Field(..., description="Minecraft username")
    password: str = Field(..., description="Password")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserInfo
