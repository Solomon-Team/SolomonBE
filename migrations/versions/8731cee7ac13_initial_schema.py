"""Initial schema

Revision ID: 8731cee7ac13
Revises:
Create Date: 2025-08-10 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8731cee7ac13"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----- Enums (create idempotently) -----
    locationtype = postgresql.ENUM(
        "TOWN", "OUTPOST", "MINE", "PORT", "OTHER",
        name="locationtype",
        create_type=False,
    )
    linedirection = postgresql.ENUM(
        "GAINED", "GIVEN",
        name="linedirection",
        create_type=False,
    )
    bind = op.get_bind()
    locationtype.create(bind, checkfirst=True)
    linedirection.create(bind, checkfirst=True)

    # ----- Users -----
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=50), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=True),
        sa.Column("structure_id", sa.String(length=50), nullable=False),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)

    # ----- Item categories -----
    op.create_table(
        "item_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.UniqueConstraint("code", name="uq_item_categories_code"),
    )

    # ----- Items -----
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False, unique=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("stack_size", sa.Integer(), nullable=False, server_default="64"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    # Case-insensitive unique name (functional unique index)
    op.execute('CREATE UNIQUE INDEX IF NOT EXISTS uq_items_name_ci ON items ((lower(name)));')

    # ----- Structure settings -----
    op.create_table(
        "structure_settings",
        sa.Column("structure_id", sa.String(length=50), primary_key=True),
        sa.Column("currency_item_id", sa.Integer(), sa.ForeignKey("items.id")),
        sa.Column("updated_by_user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ----- Item values (historical) -----
    op.create_table(
        "item_values",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("structure_id", sa.String(length=50), nullable=False),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("value_in_currency", sa.Numeric(20, 6), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("structure_id", "item_id", "effective_from", name="uq_item_values_hist"),
    )
    op.create_index("ix_item_values_lookup", "item_values", ["structure_id", "item_id", "effective_from"])
    op.execute(
        "ALTER TABLE item_values ADD CONSTRAINT chk_item_values_range "
        "CHECK (value_in_currency >= 0.001 AND value_in_currency <= 1000000)"
    )

    # ----- Locations -----
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("structure_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("type", locationtype, nullable=False, server_default="OTHER"),
        sa.Column("description", sa.Text),
        sa.Column("x", sa.Integer),
        sa.Column("y", sa.Integer),
        sa.Column("z", sa.Integer),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("structure_id", "name", name="uq_locations_structure_name"),
        sa.UniqueConstraint("structure_id", "code", name="uq_locations_structure_code"),
    )
    op.create_index("ix_locations_structure_id", "locations", ["structure_id"])
    op.create_index("ix_locations_code", "locations", ["code"])

    # ----- Trades (header) -----
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("structure_id", sa.String(length=50), nullable=False),
        sa.Column("from_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("to_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_trades_structure_ts", "trades", ["structure_id", "timestamp"])
    op.create_index("ix_trades_user_ts", "trades", ["user_id", "timestamp"])

    # ----- Trade lines -----
    op.create_table(
        "trade_lines",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trade_id", sa.Integer, sa.ForeignKey("trades.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("items.id"), nullable=False),
        sa.Column("direction", linedirection, nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("from_location_id", sa.Integer, sa.ForeignKey("locations.id")),
        sa.Column("to_location_id", sa.Integer, sa.ForeignKey("locations.id")),
    )
    op.create_index("ix_trade_lines_trade_id", "trade_lines", ["trade_id"])
    op.create_index("ix_trade_lines_item_id", "trade_lines", ["item_id"])
    op.create_index("ix_trade_lines_from_loc", "trade_lines", ["from_location_id"])
    op.create_index("ix_trade_lines_to_loc", "trade_lines", ["to_location_id"])
    op.create_index("ix_trade_lines_trade_id_item", "trade_lines", ["trade_id", "item_id"])

    # ----- Location guild masters -----
    op.create_table(
        "location_guild_masters",
        sa.Column("location_id", sa.Integer, sa.ForeignKey("locations.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("since", sa.DateTime, server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_table("location_guild_masters")
    op.drop_index("ix_trade_lines_trade_id_item", table_name="trade_lines")
    op.drop_index("ix_trade_lines_to_loc", table_name="trade_lines")
    op.drop_index("ix_trade_lines_from_loc", table_name="trade_lines")
    op.drop_index("ix_trade_lines_item_id", table_name="trade_lines")
    op.drop_index("ix_trade_lines_trade_id", table_name="trade_lines")
    op.drop_table("trade_lines")

    op.drop_index("ix_trades_user_ts", table_name="trades")
    op.drop_index("ix_trades_structure_ts", table_name="trades")
    op.drop_table("trades")

    op.drop_index("ix_locations_code", table_name="locations")
    op.drop_index("ix_locations_structure_id", table_name="locations")
    op.drop_table("locations")

    op.execute("ALTER TABLE item_values DROP CONSTRAINT IF EXISTS chk_item_values_range;")
    op.drop_index("ix_item_values_lookup", table_name="item_values")
    op.drop_table("item_values")

    op.drop_table("structure_settings")

    op.execute("DROP INDEX IF EXISTS uq_items_name_ci;")
    op.drop_table("items")

    op.drop_table("item_categories")

    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")

    # Finally drop ENUMs
    op.execute("DROP TYPE IF EXISTS locationtype")
    op.execute("DROP TYPE IF EXISTS linedirection")
