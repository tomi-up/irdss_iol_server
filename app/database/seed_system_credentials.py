import os
import logging
from datetime import datetime, timezone
from app.database.db_connection import SessionLocal
from app.models.system_credential import SystemCredential
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)

def seed_system_credentials():
    """
    Ensures that SYSTEM-001 public key is registered in central IRDSS system_credentials.
    Reads public_key.pem from mock_hospitals storage or auto-generates key pair if needed.
    """
    db = SessionLocal()
    try:
        pub_key_path = r"c:\laragon\www\mock_hospitals\storage\keys\public_key.pem"
        priv_key_path = r"c:\laragon\www\mock_hospitals\storage\keys\private_key.pem"

        pub_key_pem = None
        if os.path.exists(pub_key_path):
            with open(pub_key_path, "r") as f:
                pub_key_pem = f.read()
        else:
            # Generate keypair if mock_hospitals hasn't run yet
            os.makedirs(os.path.dirname(pub_key_path), exist_ok=True)
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            priv_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption()
            ).decode('utf-8')
            pub_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')

            with open(priv_key_path, "w") as f:
                f.write(priv_pem)
            with open(pub_key_path, "w") as f:
                f.write(pub_pem)
            pub_key_pem = pub_pem

        existing = db.query(SystemCredential).filter(SystemCredential.system_code == "SYSTEM-001").first()
        if existing:
            existing.public_key = pub_key_pem
            existing.status = "ACTIVE"
            db.commit()
            logger.info("Updated SYSTEM-001 public key in IRDSS PostgreSQL.")
        else:
            cred = SystemCredential(
                system_code="SYSTEM-001",
                system_name="Centralized HIS",
                key_id="KEY-2026-001",
                public_key=pub_key_pem,
                algorithm="RSA-2048",
                status="ACTIVE",
                created_at=datetime.now(timezone.utc),
                activated_at=datetime.now(timezone.utc)
            )
            db.add(cred)
            db.commit()
            logger.info("Registered SYSTEM-001 public key in IRDSS PostgreSQL.")

    except Exception as e:
        db.rollback()
        logger.error(f"Error seeding system credentials: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_system_credentials()
