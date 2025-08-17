from typing import Optional
from pydantic import BaseModel, Field

class MovementReasonIn(BaseModel):
    code: str = Field(..., max_length=48)
    name: str = Field(..., max_length=128)
    is_active: bool = True

class MovementReasonOut(BaseModel):
    structure_id: str
    code: str
    name: str
    is_active: bool
