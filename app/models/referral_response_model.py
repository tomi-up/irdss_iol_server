import uuid
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from app.database.db_connection import Base


class ReferralResponse(Base):
    __tablename__ = "referral_responses"
    id = Column(Integer, primary_key=True, index=True)

    # Links to the active referral transaction [cite: 197]
    referral_id = Column(
        String,
        ForeignKey("referrals.referral_id", ondelete="CASCADE"),
        nullable=False
    )

    # Links to the candidate hospital in your hospital_resources table
    hospital_name = Column(String, nullable=False)

    # States: "PENDING" (Alert sent), "ACCEPTED" (Can take patient), "REDIRECTED" (No capacity) [cite: 194]
    response_status = Column(String, default="PENDING", nullable=False)

    # Clinical M&E Audit Metrics (To track 15-to-30 minute emergency turnaround rules!) [cite: 306, 307]
    seen_at = Column(DateTime, nullable=True)  # When the receiving ER doctor opened the case details [cite: 194, 203]
    responded_at = Column(DateTime, nullable=True)  # When they clicked Accept/Redirect [cite: 194]