from typing import List, Optional
from sqlalchemy import String, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.db_connection import Base


class PatientRecords(Base):
    __tablename__ = "patient_record"

    # Internal DB Primary Key
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Universal FHIR identifier acting as a unique key for lookups
    fhir_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    gender: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Patient demographic and clinical variables for the FCM matchmaking core [cite: 94]
    age: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Precise age in whole months (e.g. 6 for a 6-month-old) -- `age` alone floors to 0 for
    # any infant under a year, which is clinically meaningless on a triage alert
    age_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary: Mapped[Optional[float]] = mapped_column(Float,nullable=True)  # Expected out-of-pocket budget limit [cite: 94]
    severity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Clinical triaging category [cite: 94]
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fitness: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Patient fitness index [cite: 94]

    # One-to-Many Relationship: A single patient can have multiple referrals over time [cite: 248]
    # We reference "Referral" as a string to completely avoid circular import issues!
    referrals: Mapped[List["Referral"]] = relationship(
        "Referral",
        back_populates="patient",
        cascade="all, delete-orphan"
    )