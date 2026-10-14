"""add patient status flags and body metrics to referrals

Revision ID: b2e6f4a8c1d9
Revises: 7d4e2c8f1a3b
Create Date: 2026-08-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2e6f4a8c1d9'
down_revision: Union[str, Sequence[str], None] = '7d4e2c8f1a3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('referrals', sa.Column('vital_height_cm', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('vital_weight_kg', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('is_pwd', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('referrals', sa.Column('is_pregnant', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('referrals', sa.Column('is_senior_citizen', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('referrals', sa.Column('has_allergy', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('referrals', sa.Column('allergy_details', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('referrals', 'allergy_details')
    op.drop_column('referrals', 'has_allergy')
    op.drop_column('referrals', 'is_senior_citizen')
    op.drop_column('referrals', 'is_pregnant')
    op.drop_column('referrals', 'is_pwd')
    op.drop_column('referrals', 'vital_weight_kg')
    op.drop_column('referrals', 'vital_height_cm')
