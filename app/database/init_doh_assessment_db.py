import logging
from app.database.db_connection import Base, engine, SessionLocal
from app.models.hospitals import Facility
from app.models.assessment_models import FacilityAssessment, AssessmentAnswer

logger = logging.getLogger(__name__)

def init_doh_assessment_db():
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("DOH Service Assessment PostgreSQL tables initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing DOH assessment tables: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    init_doh_assessment_db()
