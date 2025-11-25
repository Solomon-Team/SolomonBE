"""add_membership_status_to_users

Revision ID: dc0e8959a309
Revises: 8739c83bc7e1
Create Date: 2025-11-23 13:54:23.600749

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dc0e8959a309'
down_revision: Union[str, Sequence[str], None] = '8739c83bc7e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add membership_status column with enum constraint
    op.add_column('users', sa.Column('membership_status', sa.String(20), nullable=False, server_default='unassigned'))

    # Add check constraint for valid values
    op.create_check_constraint(
        'ck_users_membership_status',
        'users',
        "membership_status IN ('unassigned', 'guest', 'member')"
    )

    # Update existing users: if they have a structure_id, they're members
    op.execute("""
        UPDATE users
        SET membership_status = 'member'
        WHERE structure_id IS NOT NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop check constraint first
    op.drop_constraint('ck_users_membership_status', 'users', type_='check')

    # Drop column
    op.drop_column('users', 'membership_status')
