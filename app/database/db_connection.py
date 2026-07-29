import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from sqlalchemy import text

# Configure logging for production-ready output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Load variables from your .env file
load_dotenv()

# Get the URL from environment variables
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the environment variables.")

# Create the engine
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True
)

def check_db_connection() -> tuple[bool, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            return True, ""
    except Exception as e:
        return False, str(e)

# Verify database connection on startup and fail fast if down
connected, db_err = check_db_connection()
if connected:
    logger.info("Database connection test: SUCCESS (Connected successfully to the database)")
else:
    logger.error(f"Database connection test: FAILED (Could not connect to the database). Error: {db_err}")
    raise RuntimeError("Critical: Application startup aborted due to database connection failure.")

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for your models
Base = declarative_base()

# Dependency for FastAPI endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()