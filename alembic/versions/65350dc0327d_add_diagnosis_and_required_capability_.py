"""add diagnosis, chief_complaint, required_capability to referrals

Revision ID: 65350dc0327d
Revises: c1f8a92e4d6b
Create Date: 2026-08-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '65350dc0327d'
down_revision: Union[str, Sequence[str], None] = 'c1f8a92e4d6b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('referrals', sa.Column('diagnosis', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('chief_complaint', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('required_capability', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('referrals', 'required_capability')
    op.drop_column('referrals', 'chief_complaint')
    op.drop_column('referrals', 'diagnosis')
