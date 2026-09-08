"""add printable referral consent metadata

Revision ID: f7a5c8d3e2b1
Revises: e6f4a9c2d1b7
Create Date: 2026-09-08 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7a5c8d3e2b1"
down_revision: Union[str, Sequence[str], None] = "e6f4a9c2d1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("referrals", sa.Column("consent_status", sa.String(length=30), nullable=True))
    op.add_column("referrals", sa.Column("consent_method", sa.String(length=20), nullable=True))
    op.add_column("referrals", sa.Column("consent_text_version", sa.String(length=50), nullable=True))
    op.add_column("referrals", sa.Column("consent_recorded_at", sa.DateTime(), nullable=True))
    op.add_column("referrals", sa.Column("consent_witnessed_by", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("referrals", "consent_witnessed_by")
    op.drop_column("referrals", "consent_recorded_at")
    op.drop_column("referrals", "consent_text_version")
    op.drop_column("referrals", "consent_method")
    op.drop_column("referrals", "consent_status")
