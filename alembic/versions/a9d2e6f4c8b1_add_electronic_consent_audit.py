"""add electronic consent signer and document audit fields

Revision ID: a9d2e6f4c8b1
Revises: f7a5c8d3e2b1
Create Date: 2026-09-09 11:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9d2e6f4c8b1"
down_revision: Union[str, Sequence[str], None] = "f7a5c8d3e2b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("referrals", sa.Column("consent_signer_type", sa.String(length=40), nullable=True))
    op.add_column("referrals", sa.Column("consent_signer_name", sa.String(), nullable=True))
    op.add_column("referrals", sa.Column("consent_representative_relationship", sa.String(), nullable=True))
    op.add_column("referrals", sa.Column("consent_document_sha256", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("referrals", "consent_document_sha256")
    op.drop_column("referrals", "consent_representative_relationship")
    op.drop_column("referrals", "consent_signer_name")
    op.drop_column("referrals", "consent_signer_type")
