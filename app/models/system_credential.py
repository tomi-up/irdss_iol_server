from sqlalchemy import Column, Integer, String, Text, DateTime
from datetime import datetime, timezone
from app.database.db_connection import Base

class SystemCredential(Base):
    """
    Stores registered public keys for connected external systems (e.g., Centralized HIS).
    Used to verify incoming RSA-SHA256 request signatures.
    """
    __tablename__ = "system_credentials"

    id = Column(Integer, primary_key=True, index=True)
    system_code = Column(String, unique=True, index=True, default="SYSTEM-001")  # e.g., "SYSTEM-001"
    system_name = Column(String, default="Centralized HIS")
    key_id = Column(String, index=True, default="KEY-2026-001")  # e.g., "KEY-2026-001"
    public_key = Column(Text, nullable=False)  # PEM-encoded RSA 2048 Public Key
    algorithm = Column(String, default="RSA-2048")
    status = Column(String, default="ACTIVE")  # ACTIVE / REVOKED
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    activated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    revoked_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
