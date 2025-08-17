# app/services/seed.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional
import base64

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
from app.models.movement_reason import MovementReason
from app.models.inventory import PlayerInventory, PlayerInventoryLedger
from app.models.user_profile import UserProfile
from app.services.codegen import generate_unique_item_code

# ---------- Constants ----------

DEFAULT_STRUCTURE = "GPR"  # Golden Prosperity (default tenant)

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

# Per-structure movement reasons (must include at least these three)
DEFAULT_MOVEMENT_REASONS = [
    ("GAINED", "Gained"),
    ("GIVEN", "Given"),
    ("TRANSFERRED", "Transferred"),
    # nice-to-have extras for demos:
    ("MINED", "Mined"),
    ("GATHERED", "Gathered"),
    ("FARMED", "Farmed"),
    ("PURCHASED", "Purchased"),
    ("SOLD", "Sold"),
]

# System roles and permissions (per structure)
SYSTEM_ROLES = {
    "ADMIN": {
        "name": "Administrator",
        "permissions": {
            "users.admin": True,
            "rbac.view": True,
            "locations.manage": True,
            "items.manage": True,               # includes icon upload
            "valuations.manage": True,
            "trades.view_all": True,
            "inventory.admin": True,            # view any player's inventory
            "movement_reasons.manage": True,
            "users.profile.manage": True,
        },
        "is_system": True,
    },
    "GUILDMASTER": {
        "name": "Guild Master",
        "permissions": {
            "rbac.view": True,
            "locations.manage": True,
            "trades.view_all": True,
            "inventory.admin": True,
        },
        "is_system": True,
    },
    "EMPLOYEE": {
        "name": "Employee",
        "permissions": {
            "rbac.view": True,
            "inventory.view": True,            # view own inventory
        },
        "is_system": True,
    },
}

# A tiny 1x1 PNG (transparent) as a safe placeholder for icons (base64)
_PX_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII="
)
PLACEHOLDER_ICON_BYTES = base64.b64decode(_PX_PNG_B64)
PLACEHOLDER_ICON_MIME = "image/png"


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
        else:
            # update permissions if keys were added later
            if row.permissions != spec["permissions"]:
                row.permissions = spec["permissions"]
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


def _ensure_item_icons(db: Session, items_by_name: dict[str, Item]) -> None:
    """
    Store a tiny placeholder icon for each item not yet having one.
    """
    now = datetime.now(timezone.utc)
    changed = False
    for item in items_by_name.values():
        if item.icon_image is None:
            item.icon_image = PLACEHOLDER_ICON_BYTES
            item.icon_mime_type = PLACEHOLDER_ICON_MIME
            item.icon_updated_at = now
            changed = True
    if changed:
        db.commit()


def _ensure_locations(db: Session, structure_id: str) -> dict[str, Location]:
    out: dict[str, Location] = {}
    EXAMPLE_LOCATIONS: list[dict] = [
        {"name": "Golden Exchange", "type": "TOWN", "description": "Main market hub", "x": 120, "y": 64, "z": -45},
        {"name": "Mithril Mine", "type": "MINE", "description": "Deep mining outpost", "x": -340, "y": 12, "z": 220},
        {"name": "Northwatch Outpost", "type": "OUTPOST", "description": "Northern guard", "x": 540, "y": 70, "z": 410},
        {"name": "Seabreeze Port", "type": "PORT", "description": "Maritime trade hub", "x": -50, "y": 63, "z": -300},
    ]
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


def _ensure_external_locations(db: Session, structure_id: str) -> dict[str, Location]:
    """
    Ensure exactly one IMPORT and one EXPORT external location per structure.
    """
    out: dict[str, Location] = {}

    def upsert(name: str, kind: str):
        row = (
            db.query(Location)
            .filter(
                Location.structure_id == structure_id,
                Location.is_external == True,        # noqa: E712
                Location.external_kind == kind,
            ).first()
        )
        if row:
            out[name] = row
            return

        base_code = name.lower()[:32] or "loc"
        code = base_code
        i = 1
        while db.query(Location).filter_by(structure_id=structure_id, code=code).first():
            code = f"{base_code[:29]}-{i}"; i += 1

        row = Location(
            structure_id=structure_id,
            name=name,
            code=code,
            type="OTHER",
            description=f"{name} (external world)",
            is_active=True,
            is_external=True,
            external_kind=kind,
        )
        db.add(row); db.flush()
        out[name] = row

    upsert("Import", "IMPORT")
    upsert("Export", "EXPORT")
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


def _ensure_movement_reasons(db: Session, structure_id: str) -> dict[str, MovementReason]:
    out: dict[str, MovementReason] = {}
    for code, name in DEFAULT_MOVEMENT_REASONS:
        row = (
            db.query(MovementReason)
            .filter(MovementReason.structure_id == structure_id, MovementReason.code == code)
            .first()
        )
        if row is None:
            row = MovementReason(structure_id=structure_id, code=code, name=name, is_active=True)
            db.add(row); db.flush()
        out[code] = row
    db.commit()
    return out


def _ensure_user_profile(db: Session, user: User, discord: Optional[str], mc: Optional[str], notes: Optional[str] = None) -> None:
    prof = db.query(UserProfile).get(user.id)
    if prof is None:
        prof = UserProfile(user_id=user.id)
        db.add(prof)
    prof.discord_username = discord
    prof.minecraft_username = mc
    prof.notes = notes
    db.commit()


# ---------- Ledger & inventory helpers ----------

def _upsert_player_inventory(db: Session, user_id: int, item_id: int, structure_id: str, delta_qty: int) -> None:
    row = (
        db.query(PlayerInventory)
        .filter(
            PlayerInventory.user_id == user_id,
            PlayerInventory.item_id == item_id,
            PlayerInventory.structure_id == structure_id,
        )
        .first()
    )
    if row is None:
        row = PlayerInventory(
            user_id=user_id, item_id=item_id, structure_id=structure_id, quantity=0
        )
        db.add(row)
        db.flush()
    row.quantity = int(row.quantity) + int(delta_qty)
    db.commit()


def _apply_line_to_ledger_and_inventory(
    db: Session,
    structure_id: str,
    trade: Trade,
    line: TradeLine,
) -> None:
    """
    For each user party on this line, append a ledger row and update snapshot.
    - If user is 'from' side => delta = -quantity
    - If user is 'to'   side => delta = +quantity
    """
    ts = trade.timestamp
    reason = line.movement_reason_code

    # from_user side
    if line.from_user_id is not None:
        db.add(
            PlayerInventoryLedger(
                user_id=line.from_user_id,
                item_id=line.item_id,
                structure_id=structure_id,
                delta_qty=-int(line.quantity),
                trade_id=trade.id,
                trade_line_id=line.id,
                movement_reason_code=reason,
                timestamp=ts,
            )
        )
        _upsert_player_inventory(db, line.from_user_id, line.item_id, structure_id, -int(line.quantity))

    # to_user side
    if line.to_user_id is not None:
        db.add(
            PlayerInventoryLedger(
                user_id=line.to_user_id,
                item_id=line.item_id,
                structure_id=structure_id,
                delta_qty=int(line.quantity),
                trade_id=trade.id,
                trade_line_id=line.id,
                movement_reason_code=reason,
                timestamp=ts,
            )
        )
        _upsert_player_inventory(db, line.to_user_id, line.item_id, structure_id, int(line.quantity))

    db.commit()


# ---------- Example trades (include player parties) ----------

def _seed_example_trades(
    db: Session,
    structure_id: str,
    actor_user: User,  # who records the trades
    items_by_name: dict[str, Item],
    locs_by_name: dict[str, Location],
) -> None:
    any_trade = db.query(Trade.id).filter(Trade.structure_id == structure_id).first()
    if any_trade:
        return

    now = datetime.now(timezone.utc)

    # 1) Import into nation: IMPORT (external) -> Golden Exchange (internal)
    t0 = Trade(
        structure_id=structure_id,
        user_id=actor_user.id,
        timestamp=now - timedelta(hours=3),
        from_location_id=locs_by_name["Import"].id,
        to_location_id=locs_by_name["Golden Exchange"].id,
    )
    db.add(t0); db.flush()
    l0 = TradeLine(
        trade_id=t0.id,
        item_id=items_by_name["Diamond"].id,
        direction="GAINED",
        quantity=12,
        from_location_id=locs_by_name["Import"].id,
        to_location_id=locs_by_name["Golden Exchange"].id,
        movement_reason_code="PURCHASED",
    )
    db.add(l0); db.commit()  # no players involved => no ledger updates

    # 2) Player mines: Mithril Mine (location) -> employee (user)
    t1 = Trade(
        structure_id=structure_id,
        user_id=actor_user.id,
        timestamp=now - timedelta(hours=2, minutes=20),
    )
    db.add(t1); db.flush()
    l1a = TradeLine(
        trade_id=t1.id,
        item_id=items_by_name["Coal"].id,
        direction="GAINED",
        quantity=64,
        from_location_id=locs_by_name["Mithril Mine"].id,
        to_user_id=actor_user.id,
        movement_reason_code="MINED",
    )
    l1b = TradeLine(
        trade_id=t1.id,
        item_id=items_by_name["Iron Ingot"].id,
        direction="GAINED",
        quantity=32,
        from_location_id=locs_by_name["Mithril Mine"].id,
        to_user_id=actor_user.id,
        movement_reason_code="MINED",
    )
    db.add_all([l1a, l1b]); db.flush()
    _apply_line_to_ledger_and_inventory(db, structure_id, t1, l1a)
    _apply_line_to_ledger_and_inventory(db, structure_id, t1, l1b)

    # 3) Deposit to nation: employee (user) -> Golden Exchange (location)
    t2 = Trade(
        structure_id=structure_id,
        user_id=actor_user.id,
        timestamp=now - timedelta(hours=1, minutes=50),
    )
    db.add(t2); db.flush()
    l2a = TradeLine(
        trade_id=t2.id,
        item_id=items_by_name["Coal"].id,
        direction="GIVEN",
        quantity=16,
        from_user_id=actor_user.id,
        to_location_id=locs_by_name["Golden Exchange"].id,
        movement_reason_code="TRANSFERRED",
    )
    db.add(l2a); db.flush()
    _apply_line_to_ledger_and_inventory(db, structure_id, t2, l2a)

    # 4) Location -> Location (internal transfer, no player ledger)
    t3 = Trade(
        structure_id=structure_id,
        user_id=actor_user.id,
        timestamp=now - timedelta(hours=1, minutes=10),
        from_location_id=locs_by_name["Golden Exchange"].id,
        to_location_id=locs_by_name["Northwatch Outpost"].id,
    )
    db.add(t3); db.flush()
    db.add_all([
        TradeLine(
            trade_id=t3.id,
            item_id=items_by_name["Redstone"].id,
            direction="GAINED",
            quantity=64,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
            movement_reason_code="TRANSFERRED",
        ),
        TradeLine(
            trade_id=t3.id,
            item_id=items_by_name["Lapis Lazuli"].id,
            direction="GAINED",
            quantity=64,
            from_location_id=locs_by_name["Golden Exchange"].id,
            to_location_id=locs_by_name["Northwatch Outpost"].id,
            movement_reason_code="TRANSFERRED",
        ),
    ])
    db.commit()

    # 5) Player <-> Player swap: employee <-> guildmaster
    gm = (
        db.query(User)
        .filter(User.structure_id == structure_id, func.lower(User.username) == "guildmaster")
        .first()
    )
    if gm:
        t4 = Trade(
            structure_id=structure_id,
            user_id=actor_user.id,
            timestamp=now - timedelta(minutes=35),
        )
        db.add(t4); db.flush()
        # emp -> gm : Coal x8
        l4a = TradeLine(
            trade_id=t4.id,
            item_id=items_by_name["Coal"].id,
            direction="GIVEN",
            quantity=8,
            from_user_id=actor_user.id,
            to_user_id=gm.id,
            movement_reason_code="TRANSFERRED",
        )
        # gm -> emp : Emerald x1
        l4b = TradeLine(
            trade_id=t4.id,
            item_id=items_by_name["Emerald"].id,
            direction="GAINED",
            quantity=1,
            from_user_id=gm.id,
            to_user_id=actor_user.id,
            movement_reason_code="TRANSFERRED",
        )
        db.add_all([l4a, l4b]); db.flush()
        _apply_line_to_ledger_and_inventory(db, structure_id, t4, l4a)
        _apply_line_to_ledger_and_inventory(db, structure_id, t4, l4b)

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

    items_by_name = _ensure_items(db, creator_id)
    _ensure_item_icons(db, items_by_name)

    iron = items_by_name.get("Iron Ingot")
    if not iron:
        return

    structs = [r[0] for r in db.query(User.structure_id).distinct().all()]
    for sid in structs:
        _ensure_roles(db, sid)
        _ensure_structure_currency(db, sid, iron, creator_id)
        _ensure_movement_reasons(db, sid)


def seed_examples(db: Session) -> None:
    """
    Full, idempotent seed for a useful demo environment (multi-role):
      - Roles per structure
      - Users (admin, guild master, employee) with multi-role assignment
      - Categories & items (+ placeholder icons)
      - Locations (+ external import/export) & guild master assignment
      - Structure currency
      - Historical valuations
      - Movement reasons
      - Example trades including player↔location and player↔player
      - Player inventory ledger + snapshot updates
      - User profiles (discord/minecraft)
    """
    # Roles
    roles = _ensure_roles(db, DEFAULT_STRUCTURE)

    # Users (multi-role examples)
    admin = _get_or_create_user_with_roles(db, "admin", ["ADMIN"], DEFAULT_STRUCTURE, "admin123")
    gm    = _get_or_create_user_with_roles(db, "guildmaster", ["GUILDMASTER", "EMPLOYEE"], DEFAULT_STRUCTURE, "guild123")
    emp   = _get_or_create_user_with_roles(db, "employee", ["EMPLOYEE"], DEFAULT_STRUCTURE, "emp123")

    # Profiles
    _ensure_user_profile(db, admin, "admin#0001", "AdminMC", "System administrator")
    _ensure_user_profile(db, gm,    "gm#0001",    "GuildMasterMC", "Leads the guild")
    _ensure_user_profile(db, emp,   "emp#0001",   "EmployeeMC", "Demo user")

    # Taxonomy & Items (+ icons)
    _ensure_categories(db)
    items_by_name = _ensure_items(db, creator_user_id=admin.id)
    _ensure_item_icons(db, items_by_name)

    # Locations (+ external)
    locs_by_name = _ensure_locations(db, structure_id=DEFAULT_STRUCTURE)
    ext_locs = _ensure_external_locations(db, structure_id=DEFAULT_STRUCTURE)
    locs_by_name.update(ext_locs)

    # Structure currency (default = Iron Ingot)
    iron = items_by_name.get("Iron Ingot")
    if iron:
        _ensure_structure_currency(db, DEFAULT_STRUCTURE, iron, updater_user_id=admin.id)

    # Historical valuations
    _ensure_item_values(db, DEFAULT_STRUCTURE, items_by_name, creator_user_id=admin.id)

    # Movement reasons (per structure)
    _ensure_movement_reasons(db, DEFAULT_STRUCTURE)

    # Guild master responsibilities
    if "Golden Exchange" in locs_by_name:
        _ensure_guild_masters(db, locs_by_name["Golden Exchange"], [gm.id])
    if "Northwatch Outpost" in locs_by_name:
        _ensure_guild_masters(db, locs_by_name["Northwatch Outpost"], [gm.id])

    # Example trades (includes player parties + ledger updates)
    _seed_example_trades(db, DEFAULT_STRUCTURE, actor_user=emp, items_by_name=items_by_name, locs_by_name=locs_by_name)
