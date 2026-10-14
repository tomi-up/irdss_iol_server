"""add referral reasons, redirect reasons, and protected attachments

Revision ID: e6f4a9c2d1b7
Revises: b8e1d4f6a9c3
Create Date: 2026-09-06 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6f4a9c2d1b7"
down_revision: Union[str, Sequence[str], None] = "b8e1d4f6a9c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_reasons",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referral_id", sa.String(), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["referral_id"], ["referrals.referral_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("referral_id", "sort_order", name="uq_referral_reason_order"),
    )
    op.create_index("ix_referral_reasons_id", "referral_reasons", ["id"])
    op.create_index("ix_referral_reasons_referral_id", "referral_reasons", ["referral_id"])

    op.execute(
        """
        INSERT INTO referral_reasons (referral_id, code, label, is_primary, sort_order)
        SELECT referral_id, NULL, clinical_reason, TRUE, 0
        FROM referrals
        WHERE clinical_reason IS NOT NULL AND btrim(clinical_reason) <> ''
        """
    )

    op.add_column("referral_responses", sa.Column("redirect_reason_code", sa.String(length=100), nullable=True))
    op.add_column("referral_responses", sa.Column("redirect_reason_text", sa.String(length=500), nullable=True))

    op.create_table(
        "referral_attachments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("referral_id", sa.String(), nullable=False),
        sa.Column("attachment_type", sa.String(length=50), nullable=False),
        sa.Column("workflow_stage", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_facility", sa.String(length=255), nullable=False),
        sa.Column("uploaded_by_user", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["referral_id"], ["referrals.referral_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("stored_filename"),
    )
    op.create_index("ix_referral_attachments_referral_id", "referral_attachments", ["referral_id"])


def downgrade() -> None:
    op.drop_index("ix_referral_attachments_referral_id", table_name="referral_attachments")
    op.drop_table("referral_attachments")
    op.drop_column("referral_responses", "redirect_reason_text")
    op.drop_column("referral_responses", "redirect_reason_code")
    op.drop_index("ix_referral_reasons_referral_id", table_name="referral_reasons")
    op.drop_index("ix_referral_reasons_id", table_name="referral_reasons")
    op.drop_table("referral_reasons")
