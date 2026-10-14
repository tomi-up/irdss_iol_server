from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.sql import func

from app.database.db_connection import Base


class ReferralReason(Base):
    __tablename__ = "referral_reasons"
    __table_args__ = (
        UniqueConstraint("referral_id", "sort_order", name="uq_referral_reason_order"),
    )

    id = Column(Integer, primary_key=True, index=True)
    referral_id = Column(
        String,
        ForeignKey("referrals.referral_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code = Column(String(100), nullable=True)
    label = Column(String(255), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
