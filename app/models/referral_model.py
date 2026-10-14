import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
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
    # Human-readable number shown to staff (e.g. "REF-202610-00001"). The random
    # referral_id above stays the system key used in URLs, foreign keys and the
    # identity vault, so readable numbers never become guessable API handles.
    # NULL for referrals created before this column existed.
    referral_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, unique=True, index=True)

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

    # Legacy compatibility columns only. New referrals keep these NULL and place
    # direct identity at the sending and receiving hospitals.
    # They remain temporarily so referrals created before the privacy migration
    # can still be read and moved out safely.
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

    # Consent audit metadata supplied by the referring facility. A scanned signed
    # form, when available, is stored separately as a protected CONSENT_FORM attachment.
    consent_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    consent_method: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    consent_text_version: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    consent_recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    consent_witnessed_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    consent_signer_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Signer identity and relationship can disclose patient/representative identity,
    # so these values use the same AES-at-rest treatment as patient identity fields.
    consent_signer_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    consent_representative_relationship: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    consent_document_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

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

    # Phase 2 FHIR clinical coding foundation. These fields are intentionally
    # nullable so existing referrals remain valid while legacy clients continue
    # sending the original flat diagnosis, complaint, severity, and vital fields.
    diagnosis_system: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    diagnosis_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    diagnosis_display: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    diagnosis_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    chief_complaint_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    chief_complaint_system: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    chief_complaint_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    chief_complaint_display: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    triage_system: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    triage_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    triage_display: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    referral_priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)

    condition_severity_system: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    condition_severity_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    condition_severity_display: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    fhir_condition_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    fhir_service_request_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # Bidirectional ORM relationship back to Patient
    # We reference the class name as a string to completely prevent circular imports!
    patient: Mapped["PatientRecords"] = relationship("PatientRecords", back_populates="referrals")
    observations: Mapped[list["ReferralObservation"]] = relationship(
        "ReferralObservation",
        back_populates="referral",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ReferralObservation(Base):
    """Normalized FHIR Observation values linked to a referral.

    Existing ``vital_*`` columns remain in place during the compatibility
    phases. Multiple rows may share a FHIR Observation id, which supports the
    systolic and diastolic components of one blood-pressure Observation.
    """

    __tablename__ = "referral_observations"
    __table_args__ = (
        Index(
            "ix_referral_observations_referral_context",
            "referral_id",
            "measurement_context",
        ),
        Index(
            "ix_referral_observations_referral_loinc",
            "referral_id",
            "loinc_code",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    referral_id: Mapped[str] = mapped_column(
        ForeignKey("referrals.referral_id", ondelete="CASCADE"),
        nullable=False,
    )
    fhir_observation_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    loinc_code: Mapped[str] = mapped_column(String(50), nullable=False)
    display: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    value_numeric: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4), nullable=True)
    unit_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    unit_display: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    measurement_context: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="referral",
    )
    observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    referral: Mapped["Referral"] = relationship("Referral", back_populates="observations")


class ReferralNumberSequence(Base):
    """Per-month counter backing Referral.referral_number (period is YYYYMM, Philippine time)."""
    __tablename__ = "referral_number_sequences"
    period: Mapped[str] = mapped_column(String(6), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)
