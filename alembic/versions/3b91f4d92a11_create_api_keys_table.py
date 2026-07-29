"""create api_keys table with initial SHA-256 hashed hospital seed keys

Revision ID: 3b91f4d92a11
Revises: 2a80e3c81e2e
Create Date: 2026-07-28 11:00:00.000000

"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3b91f4d92a11'
down_revision: Union[str, Sequence[str], None] = '2a80e3c81e2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()


def upgrade() -> None:
    """Upgrade schema and insert initial hospital API key hashes."""
    api_keys_table = op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('hospital_name', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_keys_api_key'), 'api_keys', ['api_key'], unique=True)
    op.create_index(op.f('ix_api_keys_hospital_name'), 'api_keys', ['hospital_name'], unique=False)
    op.create_index(op.f('ix_api_keys_id'), 'api_keys', ['id'], unique=False)

    # Bulk insert initial seed API key SHA-256 hashes for target hospitals
    op.bulk_insert(
        api_keys_table,
        [
            {
                "hospital_name": "St. Jude General Hospital",
                "api_key": hash_key("irdss_api_key_stjude_9a8b7c6d5e4f3a"),
                "is_active": True
            },
            {
                "hospital_name": "City Care Medical Center",
                "api_key": hash_key("irdss_api_key_citycare_1f2e3d4c5b6a7f"),
                "is_active": True
            },
            {
                "hospital_name": "Metro Health Medical Center",
                "api_key": hash_key("irdss_api_key_metrohealth_8e7d6c5b4a3f2e"),
                "is_active": True
            }
        ]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_api_keys_id'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_hospital_name'), table_name='api_keys')
    op.drop_index(op.f('ix_api_keys_api_key'), table_name='api_keys')
    op.drop_table('api_keys')
