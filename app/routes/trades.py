# app/routes/trades.py
from decimal import Decimal

from sqlalchemy import exists, and_, or_
from sqlalchemy.orm import Session, joinedload

from fastapi import APIRouter, Depends, Response, status, HTTPException

from app.models import MovementReason, Location
from app.models.trade import Trade
from app.models.trade_line import TradeLine
from app.models.user import User
from app.schemas.trade import TradeOut, TradeLineOut, TradeCreate
from app.services.deps import get_db, get_current_user, get_current_structure, has_perm
from app.services.trade_hooks import apply_user_ledgers_and_inventory
from app.services.valuation import get_item_value_at

router = APIRouter(prefix="/trades", tags=["Trades"])


def _compute_profit(db: Session, t: Trade) -> float | None:
    structure_id = t.structure_id
    ts = t.timestamp

    lines = db.query(TradeLine).filter_by(trade_id=t.id).all()
    if not lines:
        return 0.0

    total = Decimal("0")
    for l in lines:
        v = get_item_value_at(db, structure_id, l.item_id, ts)
        if v is None:
            return None
        line_val = v * Decimal(l.quantity)
        if l.direction == "GAINED":
            total += line_val
        else:
            total -= line_val

    return float(total)


def _line_to_schema(l: TradeLine) -> TradeLineOut:
    """Single place to serialize a trade line (so we don't forget fields)."""
    return TradeLineOut(
        id=l.id,
        item_id=l.item_id,
        direction=l.direction,
        quantity=l.quantity,
        from_location_id=l.from_location_id,
        to_location_id=l.to_location_id,
        from_user_id=l.from_user_id,
        to_user_id=l.to_user_id,
        movement_reason_code=l.movement_reason_code,
    )


def _build_trade_out(db: Session, t: Trade) -> TradeOut:
    # If Trade.lines relationship exists, use it; otherwise fetch
    lines = getattr(t, "lines", None)
    if lines is None:
        lines = db.query(TradeLine).filter_by(trade_id=t.id).all()

    gained = [l for l in lines if l.direction == "GAINED"]
    given = [l for l in lines if l.direction == "GIVEN"]

    profit = _compute_profit(db, t)

    if t.user is not None:
        username = t.user.username
    elif hasattr(t, "_username_cache"):
        username = t._username_cache
    else:
        # Fallback: load the user instance then use the property
        u = db.query(User).filter(User.id == t.user_id).first()
        username = u.username if u is not None else ""

    return TradeOut(
        id=t.id,
        timestamp=t.timestamp,
        from_location_id=t.from_location_id,
        to_location_id=t.to_location_id,
        user_id=t.user_id,
        username=username,
        gained=[_line_to_schema(l) for l in gained],
        given=[_line_to_schema(l) for l in given],
        profit=profit,
    )



@router.post("", response_model=TradeOut)
def create_trade(
    payload: TradeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    structure_id: str = Depends(get_current_structure),
):
    """
    Create a trade with per-line parties (user or location) and optional header defaults.
    Enforces:
      - Exactly one FROM party (user XOR location) per line
      - Exactly one TO party (user XOR location) per line
      - Users & movement reasons must belong to caller's structure
      - Optional header locations (if provided) must belong to caller's structure
      - Optional: forbid External <-> User combos
    """
    try:
        # --- Validate optional header locations belong to structure (if provided)
        def validate_header_loc(loc_id: int | None, which: str):
            if loc_id is None:
                return
            ok = db.query(Location.id).filter(
                Location.id == loc_id,
                Location.structure_id == structure_id,
            ).first()
            if not ok:
                raise HTTPException(status_code=400, detail=f"{which} not in your structure")

        validate_header_loc(payload.from_location_id, "from_location_id")
        validate_header_loc(payload.to_location_id, "to_location_id")

        # --- Create trade header
        t = Trade(
            structure_id=structure_id,
            user_id=user.id,
            timestamp=payload.timestamp,
            from_location_id=payload.from_location_id,
            to_location_id=payload.to_location_id,
        )
        db.add(t)
        db.flush()  # get t.id

        for ln in payload.lines:
            # Resolve header defaults for locations (only when that side is a location)
            from_loc_id = ln.from_location_id or payload.from_location_id
            to_loc_id   = ln.to_location_id   or payload.to_location_id

            # Users must be in same structure
            if ln.from_user_id is not None:
                u = db.query(User).filter(
                    User.id == ln.from_user_id,
                    User.structure_id == structure_id,
                ).first()
                if not u:
                    raise HTTPException(status_code=400, detail="from_user_id not in your structure")

            if ln.to_user_id is not None:
                u = db.query(User).filter(
                    User.id == ln.to_user_id,
                    User.structure_id == structure_id,
                ).first()
                if not u:
                    raise HTTPException(status_code=400, detail="to_user_id not in your structure")

            # Movement reason must be valid (if provided)
            if ln.movement_reason_code:
                ok = db.query(MovementReason.id).filter(
                    MovementReason.structure_id == structure_id,
                    MovementReason.code == ln.movement_reason_code,
                    MovementReason.is_active.is_(True),
                ).first()
                if not ok:
                    raise HTTPException(status_code=400, detail="Invalid movement_reason_code for structure")

            # XOR per side (user XOR location), using header defaults for locations
            from_has_user = ln.from_user_id is not None
            from_has_loc  = from_loc_id is not None
            to_has_user   = ln.to_user_id is not None
            to_has_loc    = to_loc_id is not None

            if (from_has_user and from_has_loc) or (not from_has_user and not from_has_loc):
                raise HTTPException(status_code=400, detail="Provide exactly one FROM party (user XOR location; header default counts).")

            if (to_has_user and to_has_loc) or (not to_has_user and not to_has_loc):
                raise HTTPException(status_code=400, detail="Provide exactly one TO party (user XOR location; header default counts).")

            # Optional: forbid External <-> User combos
            def is_external(loc_id: int | None) -> bool:
                if loc_id is None:
                    return False
                loc = db.query(Location).filter(
                    Location.id == loc_id, Location.structure_id == structure_id
                ).first()
                return bool(loc and loc.is_external)

            if from_has_loc and is_external(from_loc_id) and to_has_user:
                raise HTTPException(status_code=400, detail="External locations cannot trade directly with users (FROM).")
            if to_has_loc and is_external(to_loc_id) and from_has_user:
                raise HTTPException(status_code=400, detail="External locations cannot trade directly with users (TO).")

            # Create line (ensure XOR by nulling the opposite party fields explicitly)
            db_line = TradeLine(
                trade_id=t.id,
                item_id=ln.item_id,
                direction=ln.direction,
                quantity=ln.quantity,
                from_user_id=ln.from_user_id if from_has_user else None,
                from_location_id=None if from_has_user else from_loc_id,
                to_user_id=ln.to_user_id if to_has_user else None,
                to_location_id=None if to_has_user else to_loc_id,
                movement_reason_code=ln.movement_reason_code,
            )
            db.add(db_line)

        db.flush()
        apply_user_ledgers_and_inventory(db, t)
        db.commit()
        db.refresh(t)
        return _build_trade_out(db, t)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create trade") from e


@router.get("", response_model=list[TradeOut])
def list_trades(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Eager-load user; lines are fetched inside _build_trade_out (safe),
    # or you can add joinedload(Trade.lines) if relationship exists.
    q = db.query(Trade).options(joinedload(Trade.user)).filter(
        Trade.structure_id == current_user.structure_id
    )
    can_view_all = has_perm(current_user, "trades.view_all")

    if not can_view_all:
      # new behavior: trades I created OR trades where any line has me as from/to user
        q = q.filter(or_(
            Trade.user_id == current_user.id,
            exists().where(and_(
                TradeLine.trade_id == Trade.id,
                or_(
                    TradeLine.from_user_id == current_user.id,
                    TradeLine.to_user_id == current_user.id,
                    ),
            )),
        ))
    trades = q.order_by(Trade.timestamp.desc()).all()
    return [_build_trade_out(db, t) for t in trades]


@router.delete("/trade-lines/{line_id}")
def delete_trade_line(
    line_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    response: Response = None,
):
    try:
        # Admin only
        if not has_perm(user, "users.admin"):
            if response is not None:
                response.status_code = status.HTTP_403_FORBIDDEN
            return {"error": "forbidden"}

        tl: TradeLine | None = db.get(TradeLine, line_id)
        if not tl:
            if response is not None:
                response.status_code = status.HTTP_404_NOT_FOUND
            return {"error": "trade line not found"}

        tr: Trade | None = db.get(Trade, tl.trade_id)
        if not tr or tr.structure_id != user.structure_id:
            if response is not None:
                response.status_code = status.HTTP_404_NOT_FOUND
            return {"error": "trade line not found"}

        trade_id = tr.id

        db.delete(tl)
        db.flush()

        remaining = db.query(TradeLine.id).filter(TradeLine.trade_id == trade_id).count()
        deleted_trade = False
        if remaining == 0:
            db.delete(tr)
            deleted_trade = True

        db.commit()
        return {"deleted_line_id": line_id, "trade_id": trade_id, "deleted_trade": deleted_trade}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to delete trade line") from e
