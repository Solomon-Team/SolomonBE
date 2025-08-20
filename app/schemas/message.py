# app/schemas/message.py
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field

class MessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    kind: str = Field(default="CHAT")  # CHAT|TITLE|ACTIONBAR|BOSSBAR
    meta: Dict[str, Any] = Field(default_factory=dict)
    to_user_ids: List[int] = Field(default_factory=list)
    to_party_ids: List[int] = Field(default_factory=list)
    deliver_after: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    requires_ack: bool = False
    priority: str = "NORMAL"

class MessageCreatedOut(BaseModel):
    message_id: int
    recipients: int

class MessageOutboxRow(BaseModel):
    id: int
    text: str
    kind: str
    created_at: datetime
    deliver_after: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    total: int
    queued: int
    failed: int
    acked: int

class MCMessage(BaseModel):
    id: int
    text: str
    kind: str
    meta: Dict[str, Any] = Field(default_factory=dict)
    expires_at: Optional[datetime] = None
    priority: str = "NORMAL"

class MCAckIn(BaseModel):
    delivered: List[int] = Field(default_factory=list)
    failed: List[int] = Field(default_factory=list)

class PartyMessageCreate(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    kind: str = Field(default="CHAT")
    meta: Dict[str, Any] = Field(default_factory=dict)
    deliver_after: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    requires_ack: bool = False
    priority: str = "NORMAL"