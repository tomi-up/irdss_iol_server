"""create admins table with named admin accounts (Tomi, Gian)

Revision ID: 7f2c1a9d4b3e
Revises: 76bc284727cb
Create Date: 2026-08-05 12:00:00.000000

"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7f2c1a9d4b3e'
down_revision: Union[str, Sequence[str], None] = '76bc284727cb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


def upgrade() -> None:
    """Upgrade schema and insert named admin account seed keys."""
    admins_table = op.create_table(
        'admins',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('totp_secret', sa.String(), nullable=True),
        sa.Column('totp_enabled', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_admins_api_key'), 'admins', ['api_key'], unique=True)
    op.create_index(op.f('ix_admins_name'), 'admins', ['name'], unique=True)
    op.create_index(op.f('ix_admins_id'), 'admins', ['id'], unique=False)

    # Bulk insert the two named admin accounts (SHA-256 hash only, raw keys handed out once)
    op.bulk_insert(
        admins_table,
        [
            {
                "name": "Tomi",
                "api_key": hash_key("irdss_admin_key_tomi_33937d443cfff634"),
                "is_active": True,
                "totp_enabled": False,
            },
            {
                "name": "Gian",
                "api_key": hash_key("irdss_admin_key_gian_89fa6acda8977ed2"),
                "is_active": True,
                "totp_enabled": False,
            },
        ]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_admins_id'), table_name='admins')
    op.drop_index(op.f('ix_admins_name'), table_name='admins')
    op.drop_index(op.f('ix_admins_api_key'), table_name='admins')
    op.drop_table('admins')
