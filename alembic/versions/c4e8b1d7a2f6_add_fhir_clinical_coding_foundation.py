"""add FHIR clinical coding foundation

Revision ID: c4e8b1d7a2f6
Revises: a9d2e6f4c8b1
Create Date: 2026-10-07 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4e8b1d7a2f6"
down_revision: Union[str, Sequence[str], None] = "a9d2e6f4c8b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    coding_columns = (
        sa.Column("diagnosis_system", sa.String(length=255), nullable=True),
        sa.Column("diagnosis_code", sa.String(length=100), nullable=True),
        sa.Column("diagnosis_display", sa.String(length=255), nullable=True),
        sa.Column("diagnosis_text", sa.Text(), nullable=True),
        sa.Column("chief_complaint_text", sa.Text(), nullable=True),
        sa.Column("chief_complaint_system", sa.String(length=255), nullable=True),
        sa.Column("chief_complaint_code", sa.String(length=100), nullable=True),
        sa.Column("chief_complaint_display", sa.String(length=255), nullable=True),
        sa.Column("triage_system", sa.String(length=255), nullable=True),
        sa.Column("triage_code", sa.String(length=50), nullable=True),
        sa.Column("triage_display", sa.String(length=100), nullable=True),
        sa.Column("referral_priority", sa.String(length=20), nullable=True),
        sa.Column("condition_severity_system", sa.String(length=255), nullable=True),
        sa.Column("condition_severity_code", sa.String(length=100), nullable=True),
        sa.Column("condition_severity_display", sa.String(length=255), nullable=True),
        sa.Column("fhir_condition_id", sa.String(length=100), nullable=True),
        sa.Column("fhir_service_request_id", sa.String(length=100), nullable=True),
    )
    for column in coding_columns:
        op.add_column("referrals", column)

    op.create_index("ix_referrals_diagnosis_code", "referrals", ["diagnosis_code"])
    op.create_index("ix_referrals_triage_code", "referrals", ["triage_code"])
    op.create_index("ix_referrals_referral_priority", "referrals", ["referral_priority"])
    op.create_index("ix_referrals_fhir_condition_id", "referrals", ["fhir_condition_id"])
    op.create_index(
        "ix_referrals_fhir_service_request_id",
        "referrals",
        ["fhir_service_request_id"],
    )

    op.create_table(
        "referral_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("referral_id", sa.String(), nullable=False),
        sa.Column("fhir_observation_id", sa.String(length=100), nullable=True),
        sa.Column("loinc_code", sa.String(length=50), nullable=False),
        sa.Column("display", sa.String(length=255), nullable=True),
        sa.Column("value_numeric", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("unit_code", sa.String(length=50), nullable=True),
        sa.Column("unit_display", sa.String(length=100), nullable=True),
        sa.Column(
            "measurement_context",
            sa.String(length=20),
            nullable=False,
            server_default="referral",
        ),
        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["referral_id"],
            ["referrals.referral_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_referral_observations_fhir_observation_id",
        "referral_observations",
        ["fhir_observation_id"],
    )
    op.create_index(
        "ix_referral_observations_referral_context",
        "referral_observations",
        ["referral_id", "measurement_context"],
    )
    op.create_index(
        "ix_referral_observations_referral_loinc",
        "referral_observations",
        ["referral_id", "loinc_code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_referral_observations_referral_loinc",
        table_name="referral_observations",
    )
    op.drop_index(
        "ix_referral_observations_referral_context",
        table_name="referral_observations",
    )
    op.drop_index(
        "ix_referral_observations_fhir_observation_id",
        table_name="referral_observations",
    )
    op.drop_table("referral_observations")

    op.drop_index("ix_referrals_fhir_service_request_id", table_name="referrals")
    op.drop_index("ix_referrals_fhir_condition_id", table_name="referrals")
    op.drop_index("ix_referrals_referral_priority", table_name="referrals")
    op.drop_index("ix_referrals_triage_code", table_name="referrals")
    op.drop_index("ix_referrals_diagnosis_code", table_name="referrals")

    for column_name in (
        "fhir_service_request_id",
        "fhir_condition_id",
        "condition_severity_display",
        "condition_severity_code",
        "condition_severity_system",
        "referral_priority",
        "triage_display",
        "triage_code",
        "triage_system",
        "chief_complaint_display",
        "chief_complaint_code",
        "chief_complaint_system",
        "chief_complaint_text",
        "diagnosis_text",
        "diagnosis_display",
        "diagnosis_code",
        "diagnosis_system",
    ):
        op.drop_column("referrals", column_name)
