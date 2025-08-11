# app/services/seed.py
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
from app.models.role import Role
from app.services.codegen import generate_unique_item_code

# ---------- Constants ----------

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

# Example “now” price points (in currency item)
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
VALUATIONS_PAST_SHIFT = timedelta(days=7)

# System roles and permissions (per structure)
SYSTEM_ROLES = {
    "ADMIN": {
        "name": "Administrator",
        "permissions": {
            "users.admin": True,
            "rbac.view": True,
            "locations.manage": True,
            "items.manage": True,
            "valuations.manage": True,
            "trades.view_all": True,
        },
        "is_system": True,
    },
    "GUILDMASTER": {
        "name": "Guild Master",
        "permissions": {
            "rbac.view": True,
            "locations.manage": True,
            "trades.view_all": True,
        },
        "is_system": True,
    },
    "EMPLOYEE": {
        "name": "Employee",
        "permissions": {
            "rbac.view": True,
        },
        "is_system": True,
    },
}

# ---------- Role helpers (multi-role) ----------

def _ensure_roles(db: Session, structure_id: str) -> dict[str, Role]:
    """
    Ensure all system roles exist for the given structure; return by code.
    """
    out: dict[str, Role] = {}
    for code, spec in SYSTEM_ROLES.items():
        row = (
            db.query(Role)
            .filter(Role.structure_id == structure_id, Role.code == code)
            .first()
        )
        if row is None:
            row = Role(
                structure_id=structure_id,
                name=spec["name"],
                code=code,
                permissions=spec["permissions"],
                is_system=spec["is_system"],
            )
            db.add(row)
            db.flush()
        out[code] = row
    db.commit()
    return out

def _get_or_create_user_with_roles(
    db: Session,
    username: str,
    role_codes: list[str],
    structure_id: str,
    password_plain: str,
) -> User:
    u = db.query(User).filter(func.lower(User.username) == username.lower()).first()
    roles = (
        db.query(Role)
        .filter(Role.structure_id == structure_id, Role.code.in_(role_codes))
        .all()
    )
    if len(roles) != len(set(role_codes)):
        missing = set(role_codes) - set(r.code for r in roles)
        raise RuntimeError(f"Missing roles {missing} for structure {structure_id}")

    if u:
        # ensure roles are assigned (idempotent upsert behavior)
        existing_codes = set(r.code for r in u.roles or [])
        new_roles = [r for r in roles if r.code not in existing_codes]
        if new_roles:
            u.roles.extend(new_roles)
            db.commit()
            db.refresh(u)
        return u

    u = User(
        username=username,
        hashed_password=hash_password(password_plain),
        structure_id=structure_id,
    )
    u.roles = roles
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

# ---------- Data helpers ----------

def _ensure_categories(db: Session) -> None:
    for code, name in CATEGORIES:
        if not db.query(ItemCategory.id).filter(ItemCategory.code == code).first():
            db.add(ItemCategory(code=code, name=name))
    db.commit()

def _ensure_items(db: Session, creator_user_id: int) -> dict[str, Item]:
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
    now = datetime.now(timezone.utc)
    past = now - VALUATIONS_PAST_SHIFT

    for point_time, valuations in [(past, VALUATIONS_NOW), (now, VALUATIONS_NOW)]:
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
    any_trade = db.query(Trade.id).filter(Trade.structure_id == structure_id).first()
    if any_trade:
        return

    now = datetime.now(timezone.utc)

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
            trade_id=t1.id, item_id=items_by_name["Iron Ingot"].id,
            direction="GAINED", quantity=128,
            from_location_id=locs_by_name["Mithril Mine"].id,
            to_location_id=locs_by_name["Golden Exchange"].id,
        ),
        TradeLine(
            trade_id=t1.id, item_id=items_by_name["Coal"].id,
            direction="GAINED", quantity=256,
            from_location_id=locs_by_name["Mithril Mine"].id,
            to_location_id=locs_by_name["Golden Exchange"].id,
        ),
    ])

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
            trade_id=t2.id, item_id=items_by_name["Gold Ingot"].id,
            direction="GIVEN", quantity=10,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
        ),
        TradeLine(
            trade_id=t2.id, item_id=items_by_name["Redstone"].id,
            direction="GAINED", quantity=64,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
        ),
        TradeLine(
            trade_id=t2.id, item_id=items_by_name["Lapis Lazuli"].id,
            direction="GAINED", quantity=64,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
        ),
    ])

    db.commit()

# ---------- Public entrypoints ----------

def seed_minimal(db: Session, admin_user_id: int | None = None) -> None:
    """
    Minimal taxonomy + currency setup across existing structures.
    """
    _ensure_categories(db)

    # pick a creator (try admin, else any user)
    creator_id = admin_user_id
    if creator_id is None:
        any_user = db.query(User).first()
        creator_id = any_user.id if any_user else 1

    _ensure_items(db, creator_id)

    iron = db.query(Item).filter(Item.code == "iron_ingot").first()
    if not iron:
        return

    structs = [r[0] for r in db.query(User.structure_id).distinct().all()]
    for sid in structs:
        _ensure_roles(db, sid)
        _ensure_structure_currency(db, sid, iron, creator_id)

def seed_examples(db: Session) -> None:
    """
    Full, idempotent seed for a useful demo environment (multi-role):
      - Roles per structure
      - Users (admin, guild master, employee) with multi-role assignment
      - Categories & items
      - Locations (+ guild master assignment)
      - Structure currency
      - Historical valuations
      - A couple of multi-line trades
    """
    # Roles
    roles = _ensure_roles(db, DEFAULT_STRUCTURE)

    # Users (multi-role examples)
    admin = _get_or_create_user_with_roles(db, "admin", ["ADMIN"], DEFAULT_STRUCTURE, "admin123")
    gm    = _get_or_create_user_with_roles(db, "guildmaster", ["GUILDMASTER", "EMPLOYEE"], DEFAULT_STRUCTURE, "guild123")
    emp   = _get_or_create_user_with_roles(db, "employee", ["EMPLOYEE"], DEFAULT_STRUCTURE, "emp123")

    # Taxonomy & Items
    _ensure_categories(db)
    items_by_name = _ensure_items(db, creator_user_id=admin.id)

    # Locations
    locs_by_name = _ensure_locations(db, structure_id=DEFAULT_STRUCTURE)

    # Structure currency (default = Iron Ingot)
    iron = items_by_name.get("Iron Ingot")
    if iron:
        _ensure_structure_currency(db, DEFAULT_STRUCTURE, iron, updater_user_id=admin.id)

    # Historical valuations
    _ensure_item_values(db, DEFAULT_STRUCTURE, items_by_name, creator_user_id=admin.id)

    # Guild master responsibilities
    if "Golden Exchange" in locs_by_name:
        _ensure_guild_masters(db, locs_by_name["Golden Exchange"], [gm.id])
    if "Northwatch Outpost" in locs_by_name:
        _ensure_guild_masters(db, locs_by_name["Northwatch Outpost"], [gm.id])

    # Example trades
    _seed_example_trades(db, DEFAULT_STRUCTURE, actor_user=emp, items_by_name=items_by_name, locs_by_name=locs_by_name)
