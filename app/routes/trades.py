# app/routes/trades.py
from decimal import Decimal
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.trade import Trade
from app.models.trade_line import TradeLine
from app.schemas.trade import TradeOut, TradeLineOut, TradeCreate
from app.models.user import User
from app.services.deps import get_db, get_current_user, get_current_structure, has_perm
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

def _build_trade_out(db: Session, t: Trade) -> TradeOut:
    lines = db.query(TradeLine).filter_by(trade_id=t.id).all()
    gained = [l for l in lines if l.direction == "GAINED"]
    given  = [l for l in lines if l.direction == "GIVEN"]

    profit = _compute_profit(db, t)

    return TradeOut(
        id=t.id,
        timestamp=t.timestamp,
        from_location_id=t.from_location_id,
        to_location_id=t.to_location_id,
        gained=[
            TradeLineOut(
                id=l.id,
                item_id=l.item_id,
                direction=l.direction,
                quantity=l.quantity,
                from_location_id=l.from_location_id,
                to_location_id=l.to_location_id,
            ) for l in gained
        ],
        given=[
            TradeLineOut(
                id=l.id,
                item_id=l.item_id,
                direction=l.direction,
                quantity=l.quantity,
                from_location_id=l.from_location_id,
                to_location_id=l.to_location_id,
            ) for l in given
        ],
        profit=profit,
    )

@router.post("", response_model=TradeOut)
def create_trade(
    payload: TradeCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    structure_id: str = Depends(get_current_structure),
):
    t = Trade(
        structure_id=structure_id,
        user_id=user.id,
        timestamp=payload.timestamp,
        from_location_id=payload.from_location_id,
        to_location_id=payload.to_location_id,
    )
    db.add(t)
    db.flush()
    for line in payload.lines:
        db.add(TradeLine(trade_id=t.id, **line.model_dump()))
    db.commit()
    db.refresh(t)
    return _build_trade_out(db, t)

@router.get("", response_model=list[TradeOut])
def list_trades(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(Trade).filter(Trade.structure_id == current_user.structure_id)
    if not has_perm(current_user, "trades.view_all"):
        q = q.filter(Trade.user_id == current_user.id)
    trades = q.order_by(Trade.timestamp.desc()).all()
    return [_build_trade_out(db, t) for t in trades]
