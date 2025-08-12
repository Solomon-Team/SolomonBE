from pydantic import BaseModel
from typing import List, Optional, Literal

ExternalKind = Optional[Literal["IMPORT", "EXPORT"]]

class InventoryItemRow(BaseModel):
    item_id: int
    item_name: str
    qty: int
    unit_value: float
    total_value: float

class InventorySummary(BaseModel):
    as_of: str
    include_external: bool
    rows: List[InventoryItemRow]
    grand_total_value: float

class ItemByLocationRow(BaseModel):
    location_id: int
    location_name: str
    is_external: bool
    external_kind: ExternalKind
    qty: int
    value: float

class LocationSummaryRow(BaseModel):
    location_id: int
    location_name: str
    is_external: bool
    external_kind: ExternalKind
    total_qty: int
    total_value: float

class LocationByItemRow(BaseModel):
    item_id: int
    item_name: str
    qty: int
    value: float
