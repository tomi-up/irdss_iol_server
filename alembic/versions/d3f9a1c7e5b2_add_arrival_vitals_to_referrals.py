"""add arrival vitals to referrals

Revision ID: d3f9a1c7e5b2
Revises: b2e6f4a8c1d9
Create Date: 2026-08-24 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3f9a1c7e5b2'
down_revision: Union[str, Sequence[str], None] = 'b2e6f4a8c1d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('referrals', sa.Column('arrival_vital_bp', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('arrival_vital_hr', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('arrival_vital_rr', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('arrival_vital_temp_c', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('arrival_vital_o2sat', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('referrals', 'arrival_vital_o2sat')
    op.drop_column('referrals', 'arrival_vital_temp_c')
    op.drop_column('referrals', 'arrival_vital_rr')
    op.drop_column('referrals', 'arrival_vital_hr')
    op.drop_column('referrals', 'arrival_vital_bp')
