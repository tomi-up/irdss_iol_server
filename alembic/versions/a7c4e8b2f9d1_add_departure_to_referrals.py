"""add departure to referrals

Revision ID: a7c4e8b2f9d1
Revises: d3f9a1c7e5b2
Create Date: 2026-08-24 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c4e8b2f9d1'
down_revision: Union[str, Sequence[str], None] = 'd3f9a1c7e5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('referrals', sa.Column('departed_at', sa.DateTime(), nullable=True))
    op.add_column('referrals', sa.Column('departure_outcome', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('departure_remarks', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('referrals', 'departure_remarks')
    op.drop_column('referrals', 'departure_outcome')
    op.drop_column('referrals', 'departed_at')
