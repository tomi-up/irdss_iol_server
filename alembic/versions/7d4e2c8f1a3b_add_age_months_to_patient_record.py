"""add age_months to patient_record

Revision ID: 7d4e2c8f1a3b
Revises: 4f1b8d3e9a2c
Create Date: 2026-08-19 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7d4e2c8f1a3b'
down_revision: Union[str, Sequence[str], None] = '4f1b8d3e9a2c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('patient_record', sa.Column('age_months', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('patient_record', 'age_months')
