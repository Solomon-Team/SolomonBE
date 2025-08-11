# app/schemas/user.py
from pydantic import BaseModel, constr
from typing import Optional, List


class UserLogin(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: constr(min_length=3, max_length=50)
    password: constr(min_length=6, max_length=128)
    role_ids: List[int]  # multiple roles

class UserUpdateRoles(BaseModel):
    role_ids: List[int]

class UserOut(BaseModel):
    id: int
    username: str
    structure_id: str
    role_ids: List[int]
    role_codes: List[Optional[str]] = []
    role_names: List[Optional[str]] = []
    class Config: from_attributes = True

    class Config:
        from_attributes = True
