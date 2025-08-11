from pydantic import BaseModel, constr
from typing import Optional, Dict, Any

class RoleCreate(BaseModel):
    name: constr(min_length=2, max_length=80)
    code: constr(min_length=2, max_length=80)
    permissions: Dict[str, Any] = {}

class RoleUpdate(BaseModel):
    name: Optional[constr(min_length=2, max_length=80)] = None
    code: Optional[constr(min_length=2, max_length=80)] = None
    permissions: Optional[Dict[str, Any]] = None

class RoleOut(BaseModel):
    id: int
    structure_id: str
    name: str
    code: str
    permissions: Dict[str, Any]
    is_system: bool

    class Config:
        from_attributes = True
