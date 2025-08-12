from datetime import datetime, timezone
from typing import List, Dict
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.services.deps import get_db, get_current_user   # ✅ this is where get_db lives
from app.models.user import User
from app.services.valuation import get_item_value_at  # you already use this in trades
from app.schemas.inventory import (
    InventorySummary, InventoryItemRow,
    ItemByLocationRow, LocationSummaryRow, LocationByItemRow
)

router = APIRouter(prefix="/inventory", tags=["inventory"])

def _as_of_or_now(as_of: datetime | None) -> datetime:
    return as_of if as_of is not None else datetime.now(timezone.utc)

# Shared CTE for movements (posts both sides when present)
_MOVEMENTS_CTE = """
WITH lines AS (
  SELECT
    tl.item_id,
    tl.quantity::bigint AS quantity,
    tl.direction,
    tl.from_location_id,
    tl.to_location_id
  FROM trade_lines tl
  JOIN trades t ON t.id = tl.trade_id
  WHERE t.structure_id = :sid AND t.timestamp <= :as_of
),
movements AS (
  SELECT item_id, from_location_id AS location_id, -quantity AS delta
  FROM lines WHERE from_location_id IS NOT NULL
  UNION ALL
  SELECT item_id, to_location_id   AS location_id, +quantity AS delta
  FROM lines WHERE to_location_id IS NOT NULL
),
mov_by_loc AS (
  SELECT m.item_id, m.location_id, SUM(m.delta)::bigint AS qty
  FROM movements m
  GROUP BY m.item_id, m.location_id
),
mov_join AS (
  SELECT
    m.item_id,
    m.location_id,
    COALESCE(m.qty, 0) AS qty,
    l.is_external,
    l.external_kind,
    l.name AS location_name
  FROM mov_by_loc m
  JOIN locations l ON l.id = m.location_id AND l.structure_id = :sid
)
"""

@router.get("/summary", response_model=InventorySummary)
def inventory_summary(
    as_of: datetime | None = Query(None),
    include_external: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asof = _as_of_or_now(as_of)

    sql = _MOVEMENTS_CTE + """
    , by_item AS (
      SELECT item_id,
             SUM(CASE WHEN :include_external THEN qty
                      WHEN is_external THEN 0
                      ELSE qty END)::bigint AS qty
      FROM mov_join
      GROUP BY item_id
    )
    SELECT i.id AS item_id, i.name AS item_name, COALESCE(b.qty,0) AS qty
    FROM items i
    LEFT JOIN by_item b ON b.item_id = i.id
    -- items table is global; we only show those with qty != 0 to keep it tidy
    WHERE COALESCE(b.qty,0) <> 0
    ORDER BY (COALESCE(b.qty,0)) DESC, i.name ASC
    """
    rows = db.execute(
        text(sql),
        {"sid": user.structure_id, "as_of": asof, "include_external": include_external},
    ).mappings().all()

    out_rows: List[InventoryItemRow] = []
    grand = 0.0
    for r in rows:
        item_id = int(r["item_id"])
        qty = int(r["qty"])
        v = get_item_value_at(db, user.structure_id, item_id, asof)
        unit = float(v or 0)
        total = round(qty * unit, 2)
        grand += total
        out_rows.append(InventoryItemRow(
            item_id=item_id,
            item_name=r["item_name"],
            qty=qty,
            unit_value=round(unit, 2),
            total_value=total,
        ))

    return InventorySummary(
        as_of=asof.isoformat(),
        include_external=include_external,
        rows=out_rows,
        grand_total_value=round(grand, 2),
    )

@router.get("/items/{item_id}/by-location", response_model=List[ItemByLocationRow])
def item_by_location(
    item_id: int,
    as_of: datetime | None = Query(None),
    include_external: bool = Query(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asof = _as_of_or_now(as_of)

    sql = _MOVEMENTS_CTE + """
    SELECT item_id, location_id, location_name, is_external, external_kind, qty
    FROM mov_join
    WHERE item_id = :item_id
      AND (:include_external OR is_external = false)
    ORDER BY is_external, location_name
    """
    rows = db.execute(
        text(sql),
        {
            "sid": user.structure_id,
            "as_of": asof,
            "include_external": include_external,
            "item_id": item_id,
        },
    ).mappings().all()

    v = get_item_value_at(db, user.structure_id, item_id, asof)
    unit = float(v or 0)
    out: List[ItemByLocationRow] = []
    for r in rows:
        qty = int(r["qty"])
        out.append(ItemByLocationRow(
            location_id=int(r["location_id"]),
            location_name=r["location_name"],
            is_external=bool(r["is_external"]),
            external_kind=r["external_kind"],
            qty=qty,
            value=round(qty * unit, 2),
        ))
    return out

@router.get("/by-location", response_model=List[LocationSummaryRow])
def inventory_by_location(
    as_of: datetime | None = Query(None),
    include_external: bool = Query(True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asof = _as_of_or_now(as_of)

    # First: qty per (item, location)
    sql = _MOVEMENTS_CTE + """
    SELECT item_id, location_id, location_name, is_external, external_kind, qty
    FROM mov_join
    WHERE (:include_external OR is_external = false)
    """
    rows = db.execute(
        text(sql),
        {"sid": user.structure_id, "as_of": asof, "include_external": include_external},
    ).mappings().all()

    # Cache unit values per item
    unit_cache: Dict[int, float] = {}
    def unit_val(i: int) -> float:
        v = unit_cache.get(i)
        if v is None:
            vv = get_item_value_at(db, user.structure_id, i, asof)
            v = float(vv or 0)
            unit_cache[i] = v
        return v

    # Aggregate to location
    agg: Dict[int, dict] = {}
    for r in rows:
        loc_id = int(r["location_id"])
        rec = agg.setdefault(loc_id, dict(
            location_id=loc_id,
            location_name=r["location_name"],
            is_external=bool(r["is_external"]),
            external_kind=r["external_kind"],
            total_qty=0,
            total_value=0.0,
        ))
        qty = int(r["qty"])
        rec["total_qty"] += qty
        rec["total_value"] += qty * unit_val(int(r["item_id"]))

    out = [
        LocationSummaryRow(
            location_id=v["location_id"],
            location_name=v["location_name"],
            is_external=v["is_external"],
            external_kind=v["external_kind"],
            total_qty=int(v["total_qty"]),
            total_value=round(float(v["total_value"]), 2),
        )
        for v in agg.values()
        if v["total_qty"] != 0
    ]
    # Show internals first, then externals; sort by value desc inside
    out.sort(key=lambda x: (x.is_external, -x.total_value, x.location_name))
    return out

@router.get("/locations/{location_id}/by-item", response_model=List[LocationByItemRow])
def location_by_item(
    location_id: int,
    as_of: datetime | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    asof = _as_of_or_now(as_of)

    sql = _MOVEMENTS_CTE + """
    SELECT item_id, qty
    FROM mov_join
    WHERE location_id = :loc
    ORDER BY item_id
    """
    rows = db.execute(
        text(sql),
        {"sid": user.structure_id, "as_of": asof, "loc": location_id},
    ).mappings().all()

    out: List[LocationByItemRow] = []
    for r in rows:
        item_id = int(r["item_id"]); qty = int(r["qty"])
        if qty == 0:  # hide zeros
            continue
        v = get_item_value_at(db, user.structure_id, item_id, asof)
        unit = float(v or 0)
        out.append(LocationByItemRow(
            item_id=item_id,
            item_name=db.execute(text("SELECT name FROM items WHERE id=:id"), {"id": item_id}).scalar() or f"#{item_id}",
            qty=qty,
            value=round(qty * unit, 2),
        ))
    return out
