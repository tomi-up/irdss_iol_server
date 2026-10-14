"""add vitals to referrals

Revision ID: 4f1b8d3e9a2c
Revises: 9c2e7a1f5b6d
Create Date: 2026-08-18 15:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4f1b8d3e9a2c'
down_revision: Union[str, Sequence[str], None] = '9c2e7a1f5b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('referrals', sa.Column('vital_bp', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('vital_hr', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('vital_rr', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('vital_temp_c', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('vital_o2sat', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('referrals', 'vital_o2sat')
    op.drop_column('referrals', 'vital_temp_c')
    op.drop_column('referrals', 'vital_rr')
    op.drop_column('referrals', 'vital_hr')
    op.drop_column('referrals', 'vital_bp')
