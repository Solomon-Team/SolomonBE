from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models.trade import Trade
from app.models.trade_line import TradeLine
from app.models.location import Location

def _fetch_location(db: Session, location_id: int, structure_id: str) -> Location:
    loc = db.query(Location).filter(Location.id == location_id, Location.structure_id == structure_id).first()
    if not loc:
        raise HTTPException(status_code=400, detail=f"Invalid location_id {location_id} for structure")
    return loc

def _validate_external_rules(db: Session, line: TradeLine, structure_id: str) -> None:
    # Pull involved locations (if any) to inspect external flags
    fl = _fetch_location(db, line.from_location_id, structure_id) if line.from_location_id is not None else None
    tl = _fetch_location(db, line.to_location_id, structure_id) if line.to_location_id is not None else None

    # Enforce structure scoping for users is handled in your route (ensure same structure)
    # External logic:
    # - If FROM is external: TO must be an internal location (and no user on 'to')
    if fl and fl.is_external:
        if line.to_user_id is not None:
            raise HTTPException(status_code=400, detail="External -> User not allowed")
        if not tl or tl.is_external:
            raise HTTPException(status_code=400, detail="External must trade with an internal location")
    # - If TO is external: FROM must be an internal location (and no user on 'from')
    if tl and tl.is_external:
        if line.from_user_id is not None:
            raise HTTPException(status_code=400, detail="User -> External not allowed")
        if not fl or fl.is_external:
            raise HTTPException(status_code=400, detail="External must trade with an internal location")

def apply_user_ledgers_and_inventory(db: Session, trade: Trade) -> None:
    """
    For every TradeLine with a user side, write ledger rows and upsert PlayerInventory.
    """
    from app.models.inventory import PlayerInventory, PlayerInventoryLedger
    from app.models.item import Item

    structure_id = trade.structure_id
    for line in trade.lines:
        _validate_external_rules(db, line, structure_id)

        if line.from_user_id is not None:
            db.add(PlayerInventoryLedger(
                user_id=line.from_user_id,
                item_id=line.item_id,
                structure_id=structure_id,
                delta_qty=-int(line.quantity),
                trade_id=trade.id,
                trade_line_id=line.id,
                movement_reason_code=line.movement_reason_code,
                timestamp=trade.timestamp,
            ))
            _upsert_snapshot(db, line.from_user_id, line.item_id, structure_id, -int(line.quantity))

        if line.to_user_id is not None:
            db.add(PlayerInventoryLedger(
                user_id=line.to_user_id,
                item_id=line.item_id,
                structure_id=structure_id,
                delta_qty=int(line.quantity),
                trade_id=trade.id,
                trade_line_id=line.id,
                movement_reason_code=line.movement_reason_code,
                timestamp=trade.timestamp,
            ))
            _upsert_snapshot(db, line.to_user_id, line.item_id, structure_id, int(line.quantity))

    db.commit()

def _upsert_snapshot(db: Session, user_id: int, item_id: int, structure_id: str, delta: int) -> None:
    from app.models.inventory import PlayerInventory
    row = (
        db.query(PlayerInventory)
        .filter(PlayerInventory.user_id == user_id,
                PlayerInventory.item_id == item_id,
                PlayerInventory.structure_id == structure_id)
        .first()
    )
    if not row:
        row = PlayerInventory(user_id=user_id, item_id=item_id, structure_id=structure_id, quantity=0)
        db.add(row); db.flush()
    row.quantity = int(row.quantity) + int(delta)
