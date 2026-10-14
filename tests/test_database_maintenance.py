from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.maintenance import count_expired_nonces, purge_expired_nonces
from app.models.used_nonce import UsedNonce


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UsedNonce.__table__.create(engine)
    return sessionmaker(bind=engine)()


def test_nonce_cleanup_only_removes_rows_outside_retention_window():
    db = _session()
    now = datetime(2026, 10, 6, 12, 0, 0)
    db.add_all(
        [
            UsedNonce(
                system_code="SYSTEM-001",
                nonce="expired",
                created_at=now - timedelta(hours=25),
            ),
            UsedNonce(
                system_code="SYSTEM-001",
                nonce="current",
                created_at=now - timedelta(minutes=10),
            ),
        ]
    )
    db.commit()

    assert count_expired_nonces(db, retention_hours=24, now=now) == 1
    assert purge_expired_nonces(db, retention_hours=24, now=now) == 1
    assert [row.nonce for row in db.query(UsedNonce).all()] == ["current"]

    db.close()
