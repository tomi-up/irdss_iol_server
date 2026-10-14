from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, JSON, DateTime, ForeignKey
from app.database.db_connection import Base

class ReferralUrgencyAudit(Base):
    __tablename__ = 'referral_urgency_audits'
    id = Column(Integer, primary_key=True)
    referral_id = Column(String, ForeignKey('referrals.referral_id', ondelete='CASCADE'), nullable=False, index=True)
    facility = Column(String(255), nullable=False)
    actor_user_id = Column(String(100), nullable=False)
    actor_role = Column(String(20), nullable=False)
    event_type = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    previous_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
