from sqlalchemy import Column, Integer, String, JSON, ForeignKey, UniqueConstraint
from app.database.db_connection import Base

class ReferralClinicalResource(Base):
    __tablename__ = 'referral_clinical_resources'
    __table_args__ = (UniqueConstraint('referral_id', 'full_url', name='uq_referral_clinical_full_url'),)
    id = Column(Integer, primary_key=True)
    referral_id = Column(String, ForeignKey('referrals.referral_id', ondelete='CASCADE'), nullable=False, index=True)
    full_url = Column(String(100), nullable=False)
    resource_type = Column(String(30), nullable=False)
    measurement_context = Column(String(20), nullable=False, default='referral')
    resource = Column(JSON, nullable=False)
