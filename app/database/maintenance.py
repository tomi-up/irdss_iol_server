import logging
import os
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database.db_connection import SessionLocal
from app.models.used_nonce import UsedNonce


logger = logging.getLogger(__name__)

DEFAULT_NONCE_RETENTION_HOURS = 24
MINIMUM_NONCE_RETENTION_HOURS = 1


def _utc_now_without_timezone() -> datetime:
    """Return UTC in the form used by the existing PostgreSQL timestamp column."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_nonce_retention_hours() -> int:
    """Read the retention period while preventing unsafe, near-zero values."""
    raw_value = os.getenv(
        "USED_NONCE_RETENTION_HOURS",
        str(DEFAULT_NONCE_RETENTION_HOURS),
    )
    try:
        configured_hours = int(raw_value)
    except (TypeError, ValueError):
        logger.warning(
            "Invalid USED_NONCE_RETENTION_HOURS=%r; using %s hours.",
            raw_value,
            DEFAULT_NONCE_RETENTION_HOURS,
        )
        return DEFAULT_NONCE_RETENTION_HOURS

    return max(configured_hours, MINIMUM_NONCE_RETENTION_HOURS)


def count_expired_nonces(
    db: Session,
    retention_hours: int | None = None,
    now: datetime | None = None,
) -> int:
    """Count nonce rows outside the replay-protection retention window."""
    hours = retention_hours or get_nonce_retention_hours()
    cutoff = (now or _utc_now_without_timezone()) - timedelta(hours=hours)
    return (
        db.query(UsedNonce)
        .filter(UsedNonce.created_at < cutoff)
        .count()
    )


def purge_expired_nonces(
    db: Session,
    retention_hours: int | None = None,
    now: datetime | None = None,
) -> int:
    """Delete nonce rows that can no longer accompany a valid signed request."""
    hours = retention_hours or get_nonce_retention_hours()
    cutoff = (now or _utc_now_without_timezone()) - timedelta(hours=hours)
    deleted = (
        db.query(UsedNonce)
        .filter(UsedNonce.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted


def run_startup_database_maintenance() -> None:
    """Run bounded, non-business-data cleanup when the API process starts."""
    db = SessionLocal()
    try:
        retention_hours = get_nonce_retention_hours()
        deleted = purge_expired_nonces(db, retention_hours=retention_hours)
        logger.info(
            "Database maintenance removed %s used nonce(s) older than %s hour(s).",
            deleted,
            retention_hours,
        )
    except Exception:
        db.rollback()
        logger.exception("Database maintenance failed; application data was not changed.")
    finally:
        db.close()

