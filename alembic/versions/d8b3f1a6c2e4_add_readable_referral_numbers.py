"""add readable referral numbers

Revision ID: d8b3f1a6c2e4
Revises: c4e8b1d7a2f6
Create Date: 2026-10-08 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8b3f1a6c2e4"
down_revision: Union[str, Sequence[str], None] = "c4e8b1d7a2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_number_sequences",
        sa.Column("period", sa.String(length=6), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False),
    )
    # Existing referrals keep their random referral_id and a NULL referral_number;
    # only referrals created after this migration receive a readable number.
    op.add_column("referrals", sa.Column("referral_number", sa.String(length=20), nullable=True))
    op.create_index("ix_referrals_referral_number", "referrals", ["referral_number"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_referrals_referral_number", table_name="referrals")
    op.drop_column("referrals", "referral_number")
    op.drop_table("referral_number_sequences")
