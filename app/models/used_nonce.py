from sqlalchemy import Column, Integer, String, DateTime, UniqueConstraint
from datetime import datetime, timezone
from app.database.db_connection import Base

class UsedNonce(Base):
    """
    Tracks used request nonces to prevent replay attacks on system-to-system requests.
    """
    __tablename__ = "used_nonces"

    id = Column(Integer, primary_key=True, index=True)
    system_code = Column(String, index=True, nullable=False)
    nonce = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        UniqueConstraint('system_code', 'nonce', name='uq_system_nonce'),
    )

