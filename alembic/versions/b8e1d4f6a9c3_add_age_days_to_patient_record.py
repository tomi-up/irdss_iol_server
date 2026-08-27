"""add age_days to patient record

Revision ID: b8e1d4f6a9c3
Revises: a7c4e8b2f9d1
Create Date: 2026-08-25 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8e1d4f6a9c3'
down_revision: Union[str, Sequence[str], None] = 'a7c4e8b2f9d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('patient_record', sa.Column('age_days', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('patient_record', 'age_days')
