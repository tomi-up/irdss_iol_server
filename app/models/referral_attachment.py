import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.database.db_connection import Base


class ReferralAttachment(Base):
    __tablename__ = "referral_attachments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    referral_id = Column(
        String,
        ForeignKey("referrals.referral_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attachment_type = Column(String(50), nullable=False)
    workflow_stage = Column(String(20), nullable=False)
    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    sha256 = Column(String(64), nullable=False)
    uploaded_by_facility = Column(String(255), nullable=False)
    uploaded_by_user = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
