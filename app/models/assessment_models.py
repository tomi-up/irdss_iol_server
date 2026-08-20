from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database.db_connection import Base

class FacilityAssessment(Base):
    """
    A facility's submitted DOH Service Assessment record in central PostgreSQL.
    """
    __tablename__ = "facility_assessments"

    id = Column(Integer, primary_key=True, index=True)
    facility_id = Column(Integer, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False, index=True)
    facility_type = Column(String, index=True, nullable=False)  # HOSPITAL / RHU / BHS
    facility_level = Column(String, nullable=True)  # LEVEL_1 / LEVEL_2 / LEVEL_3 / PRIMARY_CARE
    assessment_type = Column(String, default="Monitoring")  # New / Renewal / Monitoring
    assessment_date = Column(String, nullable=True)
    assessment_period = Column(String, nullable=True)
    assessor_name = Column(String, nullable=True)
    general_remarks = Column(Text, nullable=True)
    status = Column(String, default="SUBMITTED")  # SUBMITTED / VERIFIED / ARCHIVED
    submitted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    answers = relationship("AssessmentAnswer", back_populates="assessment", cascade="all, delete-orphan")


class AssessmentAnswer(Base):
    """
    Individual answer item recorded during a DOH Service Assessment.
    Supports rich fields for services, compliance, infrastructure, personnel counts, and equipment.
    """
    __tablename__ = "assessment_answers"

    id = Column(Integer, primary_key=True, index=True)
    facility_assessment_id = Column(Integer, ForeignKey("facility_assessments.id", ondelete="CASCADE"), nullable=False)
    category = Column(String, index=True, nullable=False)  # medical_services / nursing_service / physical_plant / minor_surgery / infrastructure / personnel / equipment / supervisory
    item_code = Column(String, index=True, nullable=False)
    item_label = Column(String, nullable=False)
    
    available = Column(Boolean, nullable=True)
    operational = Column(Boolean, nullable=True)
    adequate = Column(Boolean, nullable=True)
    compliance = Column(String, nullable=True)  # COMPLIANT / NON_COMPLIANT / NA
    count = Column(Integer, nullable=True)
    remarks = Column(Text, nullable=True)

    assessment = relationship("FacilityAssessment", back_populates="answers")
