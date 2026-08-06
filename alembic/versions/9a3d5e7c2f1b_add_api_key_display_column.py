"""add api_key_display masked-display column to api_keys, backfill seeded rows

Revision ID: 9a3d5e7c2f1b
Revises: 7f2c1a9d4b3e
Create Date: 2026-08-05 13:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a3d5e7c2f1b'
down_revision: Union[str, Sequence[str], None] = '7f2c1a9d4b3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def mask_key(raw_key: str) -> str:
    return f"{raw_key[:6]}******"


# Known raw keys for the three hospitals seeded by 3b91f4d92a11 — the only rows
# in this table old enough to predate the api_key_display column.
KNOWN_RAW_KEYS = {
    "St. Jude General Hospital": "irdss_api_key_stjude_9a8b7c6d5e4f3a",
    "City Care Medical Center": "irdss_api_key_citycare_1f2e3d4c5b6a7f",
    "Metro Health Medical Center": "irdss_api_key_metrohealth_8e7d6c5b4a3f2e",
}


def upgrade() -> None:
    op.add_column('api_keys', sa.Column('api_key_display', sa.String(), nullable=True))

    api_keys_table = sa.table(
        'api_keys',
        sa.column('hospital_name', sa.String()),
        sa.column('api_key_display', sa.String()),
    )
    connection = op.get_bind()
    for hospital_name, raw_key in KNOWN_RAW_KEYS.items():
        connection.execute(
            api_keys_table.update()
            .where(api_keys_table.c.hospital_name == hospital_name)
            .values(api_key_display=mask_key(raw_key))
        )


def downgrade() -> None:
    op.drop_column('api_keys', 'api_key_display')
