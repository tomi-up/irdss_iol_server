import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.database.db_connection import Base, engine, SessionLocal

from app.models.hospitals import Facility
from app.models.facility_user import FacilityUser
from app.models.facility_capability import FacilityCapability
from app.models.system_credential import SystemCredential
from app.models.used_nonce import UsedNonce
from app.models.assessment_models import (
    AssessmentTemplate,
    AssessmentSection,
    AssessmentItem,
    FacilityAssessment,
    AssessmentAnswer,
)

logger = logging.getLogger(__name__)

def init_db_crypto_and_templates(db: Session = None):
    """
    Creates all missing PostgreSQL tables and seeds standard DOH assessment templates.
    """
    close_db_at_end = False
    if db is None:
        db = SessionLocal()
        close_db_at_end = True

    try:
        # Create all tables defined in Base metadata if missing
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized successfully.")

        # Seed default assessment templates if not present
        hospital_l1_tpl = db.query(AssessmentTemplate).filter(
            AssessmentTemplate.facility_type == "HOSPITAL",
            AssessmentTemplate.facility_level == "LEVEL_1",
            AssessmentTemplate.version == "v1"
        ).first()

        if not hospital_l1_tpl:
            logger.info("Seeding DOH Hospital Level 1 Assessment Template...")
            h1 = AssessmentTemplate(
                name="DOH Level 1 Hospital Capability Assessment Instrument",
                facility_type="HOSPITAL",
                facility_level="LEVEL_1",
                version="v1",
                status="ACTIVE"
            )
            db.add(h1)
            db.flush()

            # Section 1: Emergency & Surgical Services
            s1 = AssessmentSection(template_id=h1.id, section_name="Emergency & Surgical Services", order_index=1)
            db.add(s1)
            db.flush()

            items_s1 = [
                AssessmentItem(section_id=s1.id, item_code="has_er_trauma", label="Emergency Trauma Operating Bay", input_type="boolean", order_index=1),
                AssessmentItem(section_id=s1.id, item_code="has_operating_room", label="Standard Operating Room (OR)", input_type="boolean", order_index=2),
                AssessmentItem(section_id=s1.id, item_code="functional_beds", label="Functional Inpatient Bed Capacity", input_type="number", order_index=3),
            ]
            db.add_all(items_s1)

            # Section 2: Critical Care & Equipment
            s2 = AssessmentSection(template_id=h1.id, section_name="Critical Care & Diagnostics", order_index=2)
            db.add(s2)
            db.flush()

            items_s2 = [
                AssessmentItem(section_id=s2.id, item_code="has_icu", label="Intensive Care Unit (ICU)", input_type="boolean", order_index=1),
                AssessmentItem(section_id=s2.id, item_code="has_ct_mri", label="CT Scan / MRI Facility", input_type="boolean", order_index=2),
                AssessmentItem(section_id=s2.id, item_code="has_xray", label="Digital X-Ray Diagnostic System", input_type="boolean", order_index=3),
                AssessmentItem(section_id=s2.id, item_code="has_blood_bank", label="Blood Bank / Blood Station", input_type="boolean", order_index=4),
            ]
            db.add_all(items_s2)

        rhu_tpl = db.query(AssessmentTemplate).filter(
            AssessmentTemplate.facility_type == "RHU",
            AssessmentTemplate.version == "v1"
        ).first()

        if not rhu_tpl:
            logger.info("Seeding DOH RHU Primary Care Assessment Template...")
            rhu = AssessmentTemplate(
                name="DOH Rural Health Unit (RHU) Primary Care Instrument",
                facility_type="RHU",
                facility_level="PRIMARY_CARE",
                version="v1",
                status="ACTIVE"
            )
            db.add(rhu)
            db.flush()

            s_rhu = AssessmentSection(template_id=rhu.id, section_name="Primary Care & Outpatient Services", order_index=1)
            db.add(s_rhu)
            db.flush()

            items_rhu = [
                AssessmentItem(section_id=s_rhu.id, item_code="has_birthing_facility", label="Birthing & Maternal Care Station", input_type="boolean", order_index=1),
                AssessmentItem(section_id=s_rhu.id, item_code="has_tb_dots", label="TB-DOTS Center", input_type="boolean", order_index=2),
                AssessmentItem(section_id=s_rhu.id, item_code="has_minor_surgery", label="Minor Ambulatory Surgery Unit", input_type="boolean", order_index=3),
            ]
            db.add_all(items_rhu)

        db.commit()
        logger.info("DOH Assessment Templates seeded successfully.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error initializing crypto & assessment templates: {e}")
    finally:
        if close_db_at_end:
            db.close()

if __name__ == "__main__":
    init_db_crypto_and_templates()
