# app/schemas/schematic.py
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ============ Schematic Schemas ============

class SchematicBase(BaseModel):
    """Base schema for schematic data."""
    name: str = Field(..., max_length=255)
    description: Optional[str] = None


class SchematicUploadResponse(BaseModel):
    """Response after uploading a schematic."""
    id: int
    name: str
    file_hash: str
    file_size: int
    original_filename: str
    uploaded_at: datetime
    message: str = "Schematic uploaded successfully"


class SchematicOut(BaseModel):
    """Full schematic metadata response."""
    id: int
    structure_id: str
    name: str
    description: Optional[str]
    file_hash: str
    file_size: int
    original_filename: str
    uploaded_by_user_id: int
    uploaded_at: datetime
    is_public: bool
    has_split_results: bool = False

    class Config:
        from_attributes = True


class SchematicListOut(BaseModel):
    """Schema for listing schematics."""
    id: int
    name: str
    description: Optional[str]
    file_size: int
    original_filename: str
    uploaded_at: datetime
    is_public: bool
    split_results_count: int = 0

    class Config:
        from_attributes = True


class SchematicUpdate(BaseModel):
    """Schema for updating schematic metadata."""
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    is_public: Optional[bool] = None


# ============ Split Result Schemas ============

class SplitResultBase(BaseModel):
    """Base schema for split result data."""
    leaf_index: int
    region_name: Optional[str] = None
    bounds_min_x: int
    bounds_min_y: int
    bounds_min_z: int
    bounds_max_x: int
    bounds_max_y: int
    bounds_max_z: int
    blocks_non_air: int
    stacks_needed: int
    material_counts: Optional[dict] = None


class SplitResultCreate(SplitResultBase):
    """Schema for creating a split result."""
    pass


class SplitResultOut(SplitResultBase):
    """Schema for split result response."""
    id: int
    schematic_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SplitResultsBatchCreate(BaseModel):
    """Schema for batch creating split results from KDTreeSplitter."""
    schematic_name: str
    total_leaves: int
    leaves: list[SplitResultCreate]


class SplitResultsBatchOut(BaseModel):
    """Response after batch creating split results."""
    schematic_id: int
    total_created: int
    message: str = "Split results saved successfully"


# ============ Load Schematic Request Schemas ============

class LoadSchematicOnClientRequest(BaseModel):
    """Request to trigger loading a schematic on a client."""
    user_id: int = Field(..., description="User ID to send the load request to")
    x: int = Field(..., description="X coordinate to place schematic")
    y: int = Field(..., description="Y coordinate to place schematic")
    z: int = Field(..., description="Z coordinate to place schematic")


class LoadSchematicOnClientResponse(BaseModel):
    """Response after triggering a schematic load."""
    request_id: str
    schematic_id: int
    target_user_id: int
    position: dict
    message: str = "Load request sent to client"
