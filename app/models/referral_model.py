import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import ForeignKey, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.db_connection import Base
from app.models.patient_model import PatientRecords


class Referral(Base):
    __tablename__ = "referrals"
    referral_id: Mapped[str] = mapped_column(
        String,
        primary_key=True,
        default=lambda: f"ref_{uuid.uuid4().hex[:12]}"
    )

    # Foreign Key pointing back to the Patient table's fhir_id
    patient_id: Mapped[str] = mapped_column(
        ForeignKey("patient_record.fhir_id", ondelete="CASCADE"),
        nullable=False
    )
    # Operational attributes mapped from the Interoperability Layer (IoL)
    referring_facility: Mapped[str] = mapped_column(String,nullable=False)  # Auto-resolved from the verified API key [1]
    receiving_facility: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # Chosen target hospital [2]
    disease_severity: Mapped[str] = mapped_column(String,nullable=False)  # Clinical categorization (e.g., "A1", "B2") [3]

    # Referral lifecycle status tracking (CREATED, SEEN, ACCEPTED, REDIRECTED, ARRIVED) [4]
    status: Mapped[str] = mapped_column(String, default="CREATED", nullable=False)
    clinical_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Performance auditing timestamps to calculate LGU response times [5]
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime,
                                                        nullable=True)  # Timestamp when receiving hospital opens the referral [6]
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime,
                                                             nullable=True)  # Timestamp when Accepted/Redirected button is clicked [7]
    arrived_at: Mapped[Optional[datetime]] = mapped_column(DateTime,
                                                           nullable=True)  # Timestamp when patient physically arrives at the facility [4]

    # Bidirectional ORM relationship back to Patient
    # We reference the class name as a string to completely prevent circular imports!
    patient: Mapped["PatientRecords"] = relationship("PatientRecords", back_populates="referrals")