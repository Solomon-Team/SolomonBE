from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session
from slugify import slugify

from app.core.security import hash_password
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.item_value import ItemValue
from app.models.location import Location
from app.models.location_guild_master import LocationGuildMaster
from app.models.structure_settings import StructureSettings
from app.models.trade import Trade
from app.models.trade_line import TradeLine
from app.models.user import User
from app.services.codegen import generate_unique_item_code


# ---------- Static example data ----------

DEFAULT_STRUCTURE = "GPR"  # Golden Prosperity (your default guild/tenant)

CATEGORIES: list[tuple[str, str]] = [
    ("ore", "Ore"), ("ingot", "Ingot"), ("gem", "Gem"), ("crop", "Crop"),
    ("food", "Food"), ("material", "Material"), ("tool", "Tool"),
    ("weapon", "Weapon"), ("armor", "Armor"), ("potion", "Potion"),
    ("mob_drop", "Mob Drop"), ("block", "Block"), ("misc", "Misc"),
]

CORE_ITEMS: list[tuple[str, str, int]] = [
    ("Iron Ingot", "ingot", 64),
    ("Gold Ingot", "ingot", 64),
    ("Diamond", "gem", 64),
    ("Emerald", "gem", 64),
    ("Coal", "ore", 64),
    ("Copper Ingot", "ingot", 64),
    ("Redstone", "ore", 64),
    ("Lapis Lazuli", "gem", 64),
]

EXAMPLE_LOCATIONS: list[dict] = [
    {"name": "Golden Exchange", "type": "TOWN", "description": "Main market hub", "x": 120, "y": 64, "z": -45},
    {"name": "Mithril Mine", "type": "MINE", "description": "Deep mining outpost", "x": -340, "y": 12, "z": 220},
    {"name": "Northwatch Outpost", "type": "OUTPOST", "description": "Northern guard", "x": 540, "y": 70, "z": 410},
    {"name": "Seabreeze Port", "type": "PORT", "description": "Maritime trade hub", "x": -50, "y": 63, "z": -300},
]

# Price points per item (in "currency item" units)
# These are example valuations and will be set for DEFAULT_STRUCTURE.
VALUATIONS_NOW: dict[str, Decimal] = {
    "Iron Ingot": Decimal("1.00"),
    "Gold Ingot": Decimal("3.50"),
    "Diamond": Decimal("12.00"),
    "Emerald": Decimal("8.00"),
    "Coal": Decimal("0.25"),
    "Copper Ingot": Decimal("0.75"),
    "Redstone": Decimal("0.30"),
    "Lapis Lazuli": Decimal("0.40"),
}
VALUATIONS_PAST_SHIFT = timedelta(days=7)  # a past price snapshot


# ---------- Helpers ----------

def _get_or_create_user(db: Session, username: str, role: str, structure_id: str, password_plain: str) -> User:
    u = db.query(User).filter(func.lower(User.username) == username.lower()).first()
    if u:
        return u
    u = User(
        username=username,
        hashed_password=hash_password(password_plain),
        role=role,
        structure_id=structure_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _ensure_categories(db: Session) -> None:
    for code, name in CATEGORIES:
        if not db.query(ItemCategory.id).filter(ItemCategory.code == code).first():
            db.add(ItemCategory(code=code, name=name))
    db.commit()


def _ensure_items(db: Session, creator_user_id: int) -> dict[str, Item]:
    """
    Returns a mapping from item name to Item row (ensures they exist).
    """
    out: dict[str, Item] = {}
    for name, cat, stack in CORE_ITEMS:
        exists = db.query(Item).filter(func.lower(Item.name) == name.lower()).first()
        if exists:
            out[name] = exists
            continue
        code = generate_unique_item_code(db, name)
        row = Item(
            name=name,
            code=code,
            category=cat,
            stack_size=stack,
            is_active=True,
            created_by_user_id=creator_user_id,
        )
        db.add(row)
        db.flush()
        out[name] = row
    db.commit()
    return out


def _ensure_locations(db: Session, structure_id: str) -> dict[str, Location]:
    """
    Creates a small set of sample locations for a structure. Returns mapping by name.
    """
    out: dict[str, Location] = {}
    for loc in EXAMPLE_LOCATIONS:
        name = loc["name"]
        existing = (
            db.query(Location)
            .filter(Location.structure_id == structure_id, Location.name == name)
            .first()
        )
        if existing:
            out[name] = existing
            continue
        base = slugify(name)[:32] or "loc"
        code = base
        i = 1
        while db.query(Location).filter_by(structure_id=structure_id, code=code).first():
            suffix = f"-{i}"
            code = f"{base[:32 - len(suffix)]}{suffix}"
            i += 1
        row = Location(
            structure_id=structure_id,
            name=name,
            code=code,
            type=loc["type"],
            description=loc.get("description"),
            x=loc.get("x"),
            y=loc.get("y"),
            z=loc.get("z"),
            is_active=True,
        )
        db.add(row)
        db.flush()
        out[name] = row
    db.commit()
    return out


def _ensure_structure_currency(db: Session, structure_id: str, currency_item: Item, updater_user_id: int | None) -> None:
    ss = db.query(StructureSettings).get(structure_id)
    if not ss:
        ss = StructureSettings(structure_id=structure_id)
        db.add(ss)
    if ss.currency_item_id is None:
        ss.currency_item_id = currency_item.id
        ss.updated_by_user_id = updater_user_id
    db.commit()


def _ensure_item_values(
    db: Session,
    structure_id: str,
    items_by_name: dict[str, Item],
    creator_user_id: int,
) -> None:
    """
    Seeds two snapshots of historical prices (past and now) for the known items.
    """
    now = datetime.now(timezone.utc)
    past = now - VALUATIONS_PAST_SHIFT

    for point_time, valuations in [(past, VALUATIONS_NOW), (now, VALUATIONS_NOW)]:
        # (using same numbers for simplicity; you can tweak if you want)
        for item_name, price in valuations.items():
            item = items_by_name.get(item_name)
            if not item:
                continue
            exists = (
                db.query(ItemValue)
                .filter(
                    ItemValue.structure_id == structure_id,
                    ItemValue.item_id == item.id,
                    ItemValue.effective_from == point_time,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                ItemValue(
                    structure_id=structure_id,
                    item_id=item.id,
                    value_in_currency=price,
                    effective_from=point_time,
                    created_by_user_id=creator_user_id,
                )
            )
    db.commit()


def _ensure_guild_masters(db: Session, location: Location, user_ids: Iterable[int]) -> None:
    # idempotent replace: clear then add
    db.query(LocationGuildMaster).filter_by(location_id=location.id).delete()
    for uid in user_ids:
        db.add(LocationGuildMaster(location_id=location.id, user_id=uid))
    db.commit()


def _seed_example_trades(
    db: Session,
    structure_id: str,
    actor_user: User,
    items_by_name: dict[str, Item],
    locs_by_name: dict[str, Location],
) -> None:
    """
    Creates a couple of example trades with multiple lines and valid from/to locations.
    Skips if any trade already exists for the structure.
    """
    any_trade = db.query(Trade.id).filter(Trade.structure_id == structure_id).first()
    if any_trade:
        return

    now = datetime.now(timezone.utc)

    # Trade A: Mining delivery to town
    t1 = Trade(
        structure_id=structure_id,
        user_id=actor_user.id,
        timestamp=now - timedelta(hours=2),
        from_location_id=locs_by_name["Mithril Mine"].id,
        to_location_id=locs_by_name["Golden Exchange"].id,
    )
    db.add(t1)
    db.flush()
    db.add_all([
        TradeLine(
            trade_id=t1.id,
            item_id=items_by_name["Iron Ingot"].id,
            direction="GAINED",
            quantity=128,
            from_location_id=locs_by_name["Mithril Mine"].id,
            to_location_id=locs_by_name["Golden Exchange"].id,
        ),
        TradeLine(
            trade_id=t1.id,
            item_id=items_by_name["Coal"].id,
            direction="GAINED",
            quantity=256,
            from_location_id=locs_by_name["Mithril Mine"].id,
            to_location_id=locs_by_name["Golden Exchange"].id,
        ),
    ])

    # Trade B: Purchase tools going to outpost; pay with gold (given)
    t2 = Trade(
        structure_id=structure_id,
        user_id=actor_user.id,
        timestamp=now - timedelta(hours=1, minutes=10),
        from_location_id=locs_by_name["Golden Exchange"].id,
        to_location_id=locs_by_name["Northwatch Outpost"].id,
    )
    db.add(t2)
    db.flush()
    db.add_all([
        TradeLine(
            trade_id=t2.id,
            item_id=items_by_name["Gold Ingot"].id,
            direction="GIVEN",
            quantity=10,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
        ),
        TradeLine(
            trade_id=t2.id,
            item_id=items_by_name["Redstone"].id,
            direction="GAINED",
            quantity=64,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
        ),
        TradeLine(
            trade_id=t2.id,
            item_id=items_by_name["Lapis Lazuli"].id,
            direction="GAINED",
            quantity=64,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
        ),
    ])

    db.commit()


# ---------- Public entrypoints ----------

def seed_minimal(db: Session, admin_user_id: int | None = None) -> None:
    """
    Kept for backward compatibility (categories + core items + default currency).
    """
    _ensure_categories(db)
    # if admin_user_id not provided, try to pick first admin or first user
    creator_id = admin_user_id
    if creator_id is None:
        admin = db.query(User).filter(User.role == "ADMIN").first()
        if admin:
            creator_id = admin.id
        else:
            any_user = db.query(User).first()
            creator_id = any_user.id if any_user else 1  # may fail if no user exists

    _ensure_items(db, creator_id)

    iron = db.query(Item).filter(Item.code == "iron_ingot").first()
    if not iron:
        return

    structs = [r[0] for r in db.query(User.structure_id).distinct().all()]
    for sid in structs:
        _ensure_structure_currency(db, sid, iron, creator_id)


def seed_examples(db: Session) -> None:
    """
    Full, idempotent seed for a useful demo environment:
      - Users (admin/guildmaster/employee) in DEFAULT_STRUCTURE
      - Categories, Items
      - Locations (+ assign guild master)
      - Structure currency
      - Item valuations (past & now)
      - A couple of example trades with multiple lines
    """
    # 1) Users
    admin = _get_or_create_user(db, "admin", "ADMIN", DEFAULT_STRUCTURE, "admin123")
    gm = _get_or_create_user(db, "guildmaster", "GUILDMASTER", DEFAULT_STRUCTURE, "guild123")
    emp = _get_or_create_user(db, "employee", "EMPLOYEE", DEFAULT_STRUCTURE, "emp123")

    # 2) Taxonomy & Items
    _ensure_categories(db)
    items_by_name = _ensure_items(db, creator_user_id=admin.id)

    # 3) Locations
    locs_by_name = _ensure_locations(db, structure_id=DEFAULT_STRUCTURE)

    # 4) Structure currency (default = Iron Ingot)
    iron = items_by_name.get("Iron Ingot")
    if iron:
        _ensure_structure_currency(db, DEFAULT_STRUCTURE, iron, updater_user_id=admin.id)

    # 5) Item valuations (historical)
    _ensure_item_values(db, DEFAULT_STRUCTURE, items_by_name, creator_user_id=admin.id)

    # 6) Assign guild masters to locations
    #    Example: GM is responsible for Golden Exchange and Outpost
    if "Golden Exchange" in locs_by_name:
        _ensure_guild_masters(db, locs_by_name["Golden Exchange"], [gm.id])
    if "Northwatch Outpost" in locs_by_name:
        _ensure_guild_masters(db, locs_by_name["Northwatch Outpost"], [gm.id])

    # 7) Example trades
    _seed_example_trades(db, DEFAULT_STRUCTURE, actor_user=emp, items_by_name=items_by_name, locs_by_name=locs_by_name)
