"""add encrypted patient identity fields to referrals

Revision ID: 9c2e7a1f5b6d
Revises: 65350dc0327d
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c2e7a1f5b6d'
down_revision: Union[str, Sequence[str], None] = '65350dc0327d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('referrals', sa.Column('patient_full_name', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('patient_dob', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('patient_phone', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('patient_address', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('patient_civil_status', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('patient_philhealth_number', sa.String(), nullable=True))
    op.add_column('referrals', sa.Column('patient_philhealth_status', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('referrals', 'patient_philhealth_status')
    op.drop_column('referrals', 'patient_philhealth_number')
    op.drop_column('referrals', 'patient_civil_status')
    op.drop_column('referrals', 'patient_address')
    op.drop_column('referrals', 'patient_phone')
    op.drop_column('referrals', 'patient_dob')
    op.drop_column('referrals', 'patient_full_name')
