import logging
from sqlalchemy import text
from app.database.db_connection import engine, Base
from app.models.hospitals import Facility
from app.models.assessment_models import FacilityAssessment, AssessmentAnswer


logger = logging.getLogger(__name__)

def migrate_doh_assessment_tables():
    with engine.connect() as conn:
        logger.info("Dropping legacy facility_assessments and assessment_answers tables...")
        conn.execute(text("DROP TABLE IF EXISTS assessment_answers CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS facility_assessments CASCADE;"))
        conn.commit()
    
    logger.info("Re-creating updated DOH assessment tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("DOH Service Assessment tables recreated successfully.")

if __name__ == "__main__":
    migrate_doh_assessment_tables()
