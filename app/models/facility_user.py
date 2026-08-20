from sqlalchemy import Column, Integer, String, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database.db_connection import Base

class FacilityUser(Base):
    """
    A per-facility login identity, issued by an IRDSS admin right after a facility is
    created (mirrors how API keys are minted as a separate step from hospital creation
    today). Today only FACILITY_ADMIN accounts are issued here — role is kept as a plain
    string rather than hardcoded to leave room for future roles.
    """
    __tablename__ = "facility_users"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="FACILITY_ADMIN")
    status = Column(String, nullable=False, default="Active")  # Active / Inactive
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login = Column(DateTime(timezone=True), nullable=True)
