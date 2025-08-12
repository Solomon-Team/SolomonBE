from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, set by Alembic:
revision = "43239f488f63"   # ← your new revision id
down_revision = "e8e285360a1f"     # ← initial schema id
branch_labels = None
depends_on = None

def upgrade():
    # 1) enum + columns
    external_kind = sa.Enum("IMPORT", "EXPORT", name="external_kind")
    external_kind.create(op.get_bind(), checkfirst=True)

    op.add_column("locations", sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("locations", sa.Column("external_kind", external_kind, nullable=True))

    # drop the server_default so future inserts rely on ORM default
    op.alter_column("locations", "is_external", server_default=None)

    # 2) constraint: if is_external then external_kind is not null
    op.create_check_constraint(
        "ck_locations_external_kind_needed",
        "locations",
        "(NOT is_external) OR (external_kind IS NOT NULL)"
    )

    # 3) partial unique index: at most one Import and one Export per structure
    op.create_index(
        "uq_locations_structure_external_kind",
        "locations",
        ["structure_id", "external_kind"],
        unique=True,
        postgresql_where=sa.text("is_external = true AND external_kind IS NOT NULL"),
    )

    # 4) performance indexes for inventory queries (if not already present)
    op.create_index("ix_locations_structure", "locations", ["structure_id"], unique=False)
    op.create_index("ix_trade_lines_trade_id", "trade_lines", ["trade_id"], unique=False)
    op.create_index("ix_trade_lines_item_id", "trade_lines", ["item_id"], unique=False)
    op.create_index("ix_trade_lines_from_loc", "trade_lines", ["from_location_id"], unique=False)
    op.create_index("ix_trade_lines_to_loc", "trade_lines", ["to_location_id"], unique=False)

def downgrade():
    # drop indexes
    op.drop_index("ix_trade_lines_to_loc", table_name="trade_lines")
    op.drop_index("ix_trade_lines_from_loc", table_name="trade_lines")
    op.drop_index("ix_trade_lines_item_id", table_name="trade_lines")
    op.drop_index("ix_trade_lines_trade_id", table_name="trade_lines")
    op.drop_index("ix_items_structure", table_name="items")
    op.drop_index("ix_locations_structure", table_name="locations")
    op.drop_index("uq_locations_structure_external_kind", table_name="locations")

    # drop constraint
    op.drop_constraint("ck_locations_external_kind_needed", "locations", type_="check")

    # drop columns
    op.drop_column("locations", "external_kind")
    op.drop_column("locations", "is_external")

    # drop enum
    external_kind = sa.Enum("IMPORT", "EXPORT", name="external_kind")
    external_kind.drop(op.get_bind(), checkfirst=True)
