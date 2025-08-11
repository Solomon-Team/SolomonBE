from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from slugify import slugify  # pip: python-slugify

from app.services.deps import get_db, get_current_user, get_current_structure, require_perm
from app.models.location import Location
from app.models.location_guild_master import LocationGuildMaster
from app.schemas.location import LocationCreate, LocationOut, GuildMasterAssign

router = APIRouter(prefix="/locations", tags=["locations"])

manage_locs = require_perm("locations.manage")

@router.get("", response_model=List[LocationOut])
def list_locations(
    only_active: bool = False,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
):
    q = db.query(Location).filter(Location.structure_id == structure_id)
    if only_active:
        q = q.filter(Location.is_active == True)  # noqa: E712
    return q.order_by(Location.name.asc()).all()

@router.post("", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    payload: LocationCreate,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    user=Depends(manage_locs),
):
    existing = (
        db.query(Location)
        .filter(Location.structure_id == structure_id, Location.name == payload.name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Location name already exists")

    base = slugify(payload.name)[:32] or "loc"
    code = base
    i = 1
    while db.query(Location).filter_by(structure_id=structure_id, code=code).first():
        suffix = f"-{i}"
        code = f"{base[:32 - len(suffix)]}{suffix}"
        i += 1

    loc = Location(structure_id=structure_id, code=code, **payload.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return loc

@router.post("/{location_id}/guildmasters", status_code=status.HTTP_204_NO_CONTENT)
def set_guild_masters(
    location_id: int,
    body: GuildMasterAssign,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
    user=Depends(manage_locs),
):
    loc = db.query(Location).filter_by(id=location_id, structure_id=structure_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Location not found")

    db.query(LocationGuildMaster).filter_by(location_id=location_id).delete()
    for uid in body.user_ids:
        db.add(LocationGuildMaster(location_id=location_id, user_id=uid))
    db.commit()
    return

@router.get("/{location_id}/inventory")
def get_location_inventory(
    location_id: int,
    db: Session = Depends(get_db),
    structure_id: str = Depends(get_current_structure),
):
    sql = """
    SELECT tl.item_id,
           SUM(
             CASE
               WHEN tl.direction = 'GAINED' AND tl.to_location_id = :loc THEN tl.quantity
               WHEN tl.direction = 'GIVEN' AND tl.from_location_id = :loc THEN -tl.quantity
               ELSE 0
             END
           ) AS qty
    FROM trade_lines tl
    JOIN trades t ON t.id = tl.trade_id
    WHERE t.structure_id = :sid
      AND (:loc = tl.from_location_id OR :loc = tl.to_location_id)
    GROUP BY tl.item_id
    HAVING SUM(
             CASE
               WHEN tl.direction = 'GAINED' AND tl.to_location_id = :loc THEN tl.quantity
               WHEN tl.direction = 'GIVEN' AND tl.from_location_id = :loc THEN -tl.quantity
               ELSE 0
             END
           ) <> 0
    """
    rows = db.execute(text(sql), {"sid": structure_id, "loc": location_id}).mappings().all()
    return [{"item_id": r["item_id"], "quantity": int(r["qty"])} for r in rows]
