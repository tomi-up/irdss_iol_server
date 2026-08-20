from sqlalchemy import Column, Integer, Boolean, ForeignKey
from app.database.db_connection import Base

class FacilityCapability(Base):
    """
    Streamlined DOH Health Facility Profiling (HFP) checklist, one row per facility.
    Replaces the old flat available_beds/emergency_equipment/medical_equipment/
    communication_systems booleans on the facility record — routing_filter.py's severity-based
    candidate matching reads from here instead. Mirrors the shape of mock_hospitals'
    `service_assessments` table. Defaults to a zeroed/all-false row created alongside each
    new facility; nothing feeds real data into it yet (a natural follow-up once a facility's
    own admin can log in and submit it, the same way mock_hospitals' Service Assessment works).
    """
    __tablename__ = "facility_capabilities"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    authorized_bed_capacity = Column(Integer, default=0)
    functional_beds = Column(Integer, default=0)

    has_icu = Column(Boolean, default=False)
    has_nicu = Column(Boolean, default=False)
    has_er_trauma = Column(Boolean, default=False)
    has_delivery_room = Column(Boolean, default=False)
    has_hemodialysis = Column(Boolean, default=False)
    has_blood_bank = Column(Boolean, default=False)
    has_ct_mri = Column(Boolean, default=False)

    has_cardiologist = Column(Boolean, default=False)
    has_obgyn = Column(Boolean, default=False)
    has_neurologist = Column(Boolean, default=False)
    has_general_surgeon = Column(Boolean, default=False)
