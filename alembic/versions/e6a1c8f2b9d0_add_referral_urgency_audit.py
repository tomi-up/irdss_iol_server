"""Add append-only clinical urgency audit history."""
from alembic import op
import sqlalchemy as sa
revision = 'e6a1c8f2b9d0'
down_revision = 'd8b3f1a6c2e4'
branch_labels = depends_on = None

def upgrade():
    op.create_table('referral_urgency_audits',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('referral_id', sa.String(), sa.ForeignKey('referrals.referral_id', ondelete='CASCADE'), nullable=False),
        sa.Column('facility', sa.String(255), nullable=False),
        sa.Column('actor_user_id', sa.String(100), nullable=False),
        sa.Column('actor_role', sa.String(20), nullable=False),
        sa.Column('event_type', sa.String(30), nullable=False),
        sa.Column('reason', sa.Text()),
        sa.Column('previous_values', sa.JSON()),
        sa.Column('new_values', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_referral_urgency_audits_referral_id', 'referral_urgency_audits', ['referral_id'])

def downgrade():
    op.drop_table('referral_urgency_audits')
