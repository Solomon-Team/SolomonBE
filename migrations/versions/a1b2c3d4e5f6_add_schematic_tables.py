"""add_schematic_tables

Revision ID: a1b2c3d4e5f6
Revises: 659830dae6ac
Create Date: 2026-01-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '659830dae6ac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create schematics table
    op.create_table('schematics',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('structure_id', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('file_hash', sa.String(length=64), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('original_filename', sa.String(length=255), nullable=False),
        sa.Column('schematic_data', sa.LargeBinary(), nullable=True),
        sa.Column('storage_path', sa.String(length=512), nullable=True),
        sa.Column('uploaded_by_user_id', sa.Integer(), nullable=False),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_public', sa.Boolean(), nullable=False, default=False),
        sa.ForeignKeyConstraint(['structure_id'], ['structures.id'], ),
        sa.ForeignKeyConstraint(['uploaded_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_schematics_structure_id'), 'schematics', ['structure_id'], unique=False)
    op.create_index('ix_schematic_struct_name', 'schematics', ['structure_id', 'name'], unique=False)
    op.create_index('ix_schematic_struct_uploaded', 'schematics', ['structure_id', 'uploaded_at'], unique=False)
    op.create_index('ix_schematic_hash', 'schematics', ['file_hash'], unique=False)

    # Create schematic_split_results table
    op.create_table('schematic_split_results',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('schematic_id', sa.Integer(), nullable=False),
        sa.Column('leaf_index', sa.Integer(), nullable=False),
        sa.Column('region_name', sa.String(length=255), nullable=True),
        sa.Column('bounds_min_x', sa.Integer(), nullable=False),
        sa.Column('bounds_min_y', sa.Integer(), nullable=False),
        sa.Column('bounds_min_z', sa.Integer(), nullable=False),
        sa.Column('bounds_max_x', sa.Integer(), nullable=False),
        sa.Column('bounds_max_y', sa.Integer(), nullable=False),
        sa.Column('bounds_max_z', sa.Integer(), nullable=False),
        sa.Column('blocks_non_air', sa.Integer(), nullable=False),
        sa.Column('stacks_needed', sa.Integer(), nullable=False),
        sa.Column('material_counts', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['schematic_id'], ['schematics.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_split_result_schematic', 'schematic_split_results', ['schematic_id'], unique=False)
    op.create_index('ix_split_result_schematic_leaf', 'schematic_split_results', ['schematic_id', 'leaf_index'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop schematic_split_results table
    op.drop_index('ix_split_result_schematic_leaf', table_name='schematic_split_results')
    op.drop_index('ix_split_result_schematic', table_name='schematic_split_results')
    op.drop_table('schematic_split_results')

    # Drop schematics table
    op.drop_index('ix_schematic_hash', table_name='schematics')
    op.drop_index('ix_schematic_struct_uploaded', table_name='schematics')
    op.drop_index('ix_schematic_struct_name', table_name='schematics')
    op.drop_index(op.f('ix_schematics_structure_id'), table_name='schematics')
    op.drop_table('schematics')
