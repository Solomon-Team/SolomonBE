"""magic_auth_system_redesign

Revision ID: 8739c83bc7e1
Revises: 47d939edac76
Create Date: 2025-11-22 19:22:23.043783

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8739c83bc7e1'
down_revision: Union[str, Sequence[str], None] = '47d939edac76'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Fresh start for magic auth system."""

    # ===== Drop existing auth tables (in reverse dependency order) =====
    op.execute("DROP TABLE IF EXISTS user_roles CASCADE")
    op.execute("DROP TABLE IF EXISTS user_profiles CASCADE")
    op.execute("DROP TABLE IF EXISTS location_guild_masters CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS roles CASCADE")

    # ===== Create structures table =====
    op.create_table(
        'structures',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(120), nullable=False),
        sa.Column('display_name', sa.String(120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )
    op.create_index('ix_structures_is_active', 'structures', ['is_active'])

    # ===== Create roles table (with structure FK and role types) =====
    op.create_table(
        'roles',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('structure_id', sa.String(50), nullable=False),
        sa.Column('role_type', sa.String(20), nullable=False),  # OWNER, ADMIN, MEMBER, CUSTOM
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('permissions', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('is_custom', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['structure_id'], ['structures.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('structure_id', 'role_type', 'name', name='uq_roles_structure_type_name'),
    )
    op.create_index('ix_roles_structure', 'roles', ['structure_id'])

    # ===== Create users table (new design with mc_uuid as primary identifier) =====
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('mc_uuid', sa.String(36), nullable=False, unique=True),  # Primary identifier
        sa.Column('mc_name', sa.String(16), nullable=False),  # Minecraft username
        sa.Column('login_name', sa.String(50), nullable=True, unique=True),  # Website username (optional)
        sa.Column('hashed_password', sa.String(255), nullable=True),  # Password (optional)
        sa.Column('has_password', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('structure_id', sa.String(50), nullable=True),  # Current structure (nullable)
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['structure_id'], ['structures.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_users_mc_uuid', 'users', ['mc_uuid'], unique=True)
    op.create_index('ix_users_login_name', 'users', ['login_name'], unique=True)
    op.create_index('ix_users_structure', 'users', ['structure_id'])

    # ===== Create user_roles junction table =====
    op.create_table(
        'user_roles',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('role_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('user_id', 'role_id'),
    )

    # ===== Create user_profiles table =====
    op.create_table(
        'user_profiles',
        sa.Column('user_id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('discord_username', sa.String(64), nullable=True),
        sa.Column('notes', sa.String(1024), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )

    # ===== Create magic_login_tokens table =====
    op.create_table(
        'magic_login_tokens',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('token', sa.String(64), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('mc_uuid', sa.String(36), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_magic_tokens_token', 'magic_login_tokens', ['token'], unique=True)
    op.create_index('ix_magic_tokens_expires', 'magic_login_tokens', ['expires_at'])
    op.create_index('ix_magic_tokens_user', 'magic_login_tokens', ['user_id'])

    # ===== Create structure_join_codes table =====
    op.create_table(
        'structure_join_codes',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('code', sa.String(16), nullable=False, unique=True),
        sa.Column('structure_id', sa.String(50), nullable=False),
        sa.Column('created_by_user_id', sa.Integer(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),  # NULL = never expires
        sa.Column('max_uses', sa.Integer(), nullable=True),  # NULL = unlimited
        sa.Column('used_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['structure_id'], ['structures.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='CASCADE'),
    )
    op.create_index('ix_join_codes_code', 'structure_join_codes', ['code'], unique=True)
    op.create_index('ix_join_codes_structure', 'structure_join_codes', ['structure_id'])
    op.create_index('ix_join_codes_active', 'structure_join_codes', ['is_active', 'expires_at'])

    # ===== Create auth_audit_log table =====
    op.create_table(
        'auth_audit_log',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),  # magic_link_request, magic_login, password_set, login_success, login_failed
        sa.Column('mc_uuid', sa.String(36), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_auth_audit_user', 'auth_audit_log', ['user_id', 'created_at'])
    op.create_index('ix_auth_audit_event', 'auth_audit_log', ['event_type', 'created_at'])
    op.create_index('ix_auth_audit_mc', 'auth_audit_log', ['mc_uuid'])

    # ===== Recreate location_guild_masters (it depends on users) =====
    op.create_table(
        'location_guild_masters',
        sa.Column('location_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('since', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['location_id'], ['locations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('location_id', 'user_id')
    )


def downgrade() -> None:
    """Downgrade schema - drop new tables."""
    op.drop_table('auth_audit_log')
    op.drop_table('structure_join_codes')
    op.drop_table('magic_login_tokens')
    op.drop_table('location_guild_masters')
    op.drop_table('user_profiles')
    op.drop_table('user_roles')
    op.drop_table('users')
    op.drop_table('roles')
    op.drop_table('structures')
