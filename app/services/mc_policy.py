# app/services/mc_policy.py
from __future__ import annotations
from typing import Dict, Tuple
from time import time
from sqlalchemy.orm import Session
from app.models.message_position_policy import MessagePositionPolicy

_DEFAULT_POSITION = "BOTTOM"
_TTL_SECONDS = 60

# simple TTL cache: key=(structure_id, kind) -> (value, expires_at)
_cache: Dict[Tuple[str, str], Tuple[str, float]] = {}

def _now() -> float:
    return time()

def get_position(db: Session, structure_id: str, kind: str) -> str:
    k = (structure_id, kind.upper() if kind else kind)
    v = _cache.get(k)
    if v and v[1] > _now():
        return v[0]

    # 1) structure-specific override
    row = (
        db.query(MessagePositionPolicy.position)
        .filter(MessagePositionPolicy.structure_id == structure_id,
                MessagePositionPolicy.kind == k[1])
        .first()
    )
    if row:
        pos = row[0]
        _cache[k] = (pos, _now() + _TTL_SECONDS)
        return pos

    # 2) global default
    row = (
        db.query(MessagePositionPolicy.position)
        .filter(MessagePositionPolicy.structure_id.is_(None),
                MessagePositionPolicy.kind == k[1])
        .first()
    )
    if row:
        pos = row[0]
        _cache[k] = (pos, _now() + _TTL_SECONDS)
        return pos

    # 3) hard default
    _cache[k] = (_DEFAULT_POSITION, _now() + _TTL_SECONDS)
    return _DEFAULT_POSITION

def invalidate(structure_id: str, kind: str) -> None:
    _cache.pop((structure_id, kind.upper()), None)
