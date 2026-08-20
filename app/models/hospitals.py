from sqlalchemy import Column, Integer, String, Float, Date
from app.database.db_connection import Base

class Facility(Base):
    """
    A registered health facility (BHS/RHU/Hospital) in the IRDSS network.
    Renamed from the original HospitalResources/hospital_resources — inventory/capacity
    data now lives on FacilityCapability (app/models/facility_capability.py), keeping this
    model focused on identity, location, contact, and licensing.
    """
    __tablename__ = "facilities"

    id = Column(Integer, primary_key=True, index=True)

    # Facility Information
    facility_code = Column(String, unique=True, index=True)  # "FAC-000001" style, generated from id
    facility_name = Column(String, index=True)
    facility_type = Column(String)  # BHS / RHU / Level 1-3 Hospital (DOH tier enum, validated in schema)
    ownership = Column(String)  # Government / Private
    facility_head = Column(String, nullable=True)

    # Location
    region = Column(String, nullable=True)
    province = Column(String, nullable=True)
    municipality = Column(String, nullable=True)
    barangay = Column(String, nullable=True)
    address = Column(String, nullable=True)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)

    # Contact
    contact_number = Column(String, nullable=True)
    email = Column(String, nullable=True)

    # Licensing (LTO - License to Operate)
    lto_number = Column(String, nullable=True)
    lto_type = Column(String, nullable=True)
    lto_issue_date = Column(Date, nullable=True)
    lto_expiration_date = Column(Date, nullable=True)
    lto_status = Column(String, nullable=True)  # Active / Expired / Suspended / Pending
    lto_file_path = Column(String, nullable=True)

    # System
    facility_status = Column(String, default="Active")  # Active / Inactive

    # AI routing engine bookkeeping — not part of facility registration, kept as-is
    # The optimized target calculated by the background PSO job [cite: 110]
    pso_daily_routing_limit = Column(Integer, default=5)
    # Current daily acceptances (resets to 0 every midnight) [cite: 110]
    referrals_accepted_today = Column(Integer, default=0)


# Backward-compatibility alias
HospitalResources = Facility

