# app/models/__init__.py
from app.core.database import Base  # re-export for convenience

# Import all model modules so their tables attach to Base.metadata
from app.models.structure import Structure
from app.models.user import User
from app.models.item import Item
from app.models.item_category import ItemCategory
from app.models.item_value import ItemValue
from app.models.structure_settings import StructureSettings
from app.models.trade import Trade
from app.models.trade_line import TradeLine
from app.models.location import Location
from app.models.location_guild_master import LocationGuildMaster
from app.models.role import Role
from app.models.movement_reason import MovementReason
from app.models.inventory import PlayerInventory, PlayerInventoryLedger
from app.models.user_profile import UserProfile
from app.models.magic_login_token import MagicLoginToken
from app.models.structure_join_code import StructureJoinCode
from app.models.auth_audit_log import AuthAuditLog
from app.models.mc import MCLivePlayer, MCPlayerInventorySnapshot, MCContainerSnapshot, MCIngestToken, MCPositionHistory
from app.models.chest_sync import ChestSyncSnapshot, ChestSyncHistory
from app.models.party import Party, PartyMember
from app.models.message import Message, MessageTarget, MessageRecipientStatus
from app.models.message_position_policy import MessagePositionPolicy
from app.models.schematic import Schematic, SchematicSplitResult

__all__ = [
    "Base",
    "Structure",
    "User",
    "Item",
    "ItemCategory",
    "ItemValue",
    "StructureSettings",
    "Trade",
    "TradeLine",
    "Location",
    "LocationGuildMaster",
    "Role",
    "MovementReason",
    "PlayerInventory",
    "PlayerInventoryLedger",
    "UserProfile",
    "MagicLoginToken",
    "StructureJoinCode",
    "AuthAuditLog",
    "MCIngestToken",
    "MCPositionHistory",
    "MCLivePlayer",
    "MCContainerSnapshot",
    "MCPlayerInventorySnapshot",
    "ChestSyncSnapshot",
    "ChestSyncHistory",
    "Party",
    "PartyMember",
    "Message",
    "MessageTarget",
    "MessageRecipientStatus",
    "MessagePositionPolicy",
    "Schematic",
    "SchematicSplitResult"
]
