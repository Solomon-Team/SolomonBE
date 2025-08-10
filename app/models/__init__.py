# app/models/__init__.py
from app.core.database import Base  # re-export for convenience

# Import all model modules so their tables attach to Base.metadata
from app.models.user import User
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.item_value import ItemValue
from app.models.structure_settings import StructureSettings
from app.models.trade import Trade
from app.models.trade_line import TradeLine
from app.models.location import Location
from app.models.location_guild_master import LocationGuildMaster

__all__ = [
    "Base",
    "User",
    "Item",
    "ItemCategory",
    "ItemValue",
    "StructureSettings",
    "Trade",
    "TradeLine",
    "Location",
    "LocationGuildMaster",
]
