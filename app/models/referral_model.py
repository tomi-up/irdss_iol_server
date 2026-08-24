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

    # Non-reversible SHA-256 hash of (Full Name + Birthdate + Sex), lets the central IoL track
    # whether a patient already has an active referral network-wide without storing their PII [cite: 13, 110, 184]
    patient_code: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Referral lifecycle status tracking (CREATED, SEEN, ACCEPTED, REDIRECTED, ARRIVED) [4]
    status: Mapped[str] = mapped_column(String, default="CREATED", nullable=False)
    clinical_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Clinical context captured from the referring facility's FHIR payload, used to
    # derive `required_capability` — never fed back into the FCM distance score itself,
    # only used as a hard pre-filter alongside severity in routing_filter.py
    diagnosis: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    chief_complaint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # Comma-separated FacilityCapability column names (e.g. "has_obgyn,has_delivery_room")
    # that a candidate facility must have to be broadcast this referral
    required_capability: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # AES-encrypted patient identity fields (see app.utils.security.aes_encrypt/aes_decrypt).
    # Deliberately stored here on Referral, never on PatientRecords -- PatientRecords feeds
    # the FCM matching engine and must stay non-identifying. These are only ever decrypted by
    # GET /api/v1/referral/{id}/patient-details, gated on receiving_facility == caller.
    patient_full_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    patient_dob: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    patient_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    patient_address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    patient_civil_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    patient_philhealth_number: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    patient_philhealth_status: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Vitals recorded by the referring doctor/nurse at the time of referral -- sent as FHIR
    # extensions in the initiate payload but previously silently dropped (only chiefComplaint
    # was ever parsed). Kept as strings to mirror mock_hospitals' initiated_referrals shape.
    vital_bp: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vital_hr: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vital_rr: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vital_temp_c: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vital_o2sat: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vital_height_cm: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    vital_weight_kg: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Vitals recorded by the receiving facility at the moment the patient physically
    # arrives (distinct from vital_* above, which are the referring facility's readings
    # at referral time) -- a patient's condition can change meaningfully in transport,
    # so this captures a second, independent snapshot rather than overwriting the first.
    arrival_vital_bp: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    arrival_vital_hr: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    arrival_vital_rr: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    arrival_vital_temp_c: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    arrival_vital_o2sat: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Patient status flags entered by the referring doctor/nurse at referral time --
    # relevant to how the receiving facility triages/accepts, not just post-acceptance viewing
    is_pwd: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_pregnant: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_senior_citizen: Mapped[bool] = mapped_column(default=False, nullable=False)
    has_allergy: Mapped[bool] = mapped_column(default=False, nullable=False)
    allergy_details: Mapped[Optional[str]] = mapped_column(String, nullable=True)

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

    # Marks the end of this facility's episode of care for the patient -- lets the
    # ORIGINAL referring hospital see what became of them after arrival (discharged,
    # transferred onward, deceased, left against medical advice) instead of the trail
    # going cold once arrived_at is stamped.
    departed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    departure_outcome: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # DISCHARGED / TRANSFERRED / DECEASED / LEFT_AMA
    departure_remarks: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Bidirectional ORM relationship back to Patient
    # We reference the class name as a string to completely prevent circular imports!
    patient: Mapped["PatientRecords"] = relationship("PatientRecords", back_populates="referrals")