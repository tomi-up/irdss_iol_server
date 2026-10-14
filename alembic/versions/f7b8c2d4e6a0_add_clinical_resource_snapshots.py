"""Store scoped, privacy-minimized clinical FHIR resources."""
from alembic import op
import sqlalchemy as sa
revision = 'f7b8c2d4e6a0'
down_revision = 'e6a1c8f2b9d0'
branch_labels = depends_on = None

def upgrade():
    op.create_table('referral_clinical_resources',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('referral_id', sa.String(), sa.ForeignKey('referrals.referral_id', ondelete='CASCADE'), nullable=False),
        sa.Column('full_url', sa.String(100), nullable=False),
        sa.Column('resource_type', sa.String(30), nullable=False),
        sa.Column('measurement_context', sa.String(20), nullable=False),
        sa.Column('resource', sa.JSON(), nullable=False),
        sa.UniqueConstraint('referral_id', 'full_url', name='uq_referral_clinical_full_url'))
    op.create_index('ix_referral_clinical_resources_referral_id', 'referral_clinical_resources', ['referral_id'])

def downgrade(): op.drop_table('referral_clinical_resources')
