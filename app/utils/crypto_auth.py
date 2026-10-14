import base64
import hashlib
import time
import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import Request, HTTPException, Depends, status
from sqlalchemy.orm import Session
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

from app.database.db_connection import get_db
from app.models.system_credential import SystemCredential
from app.models.used_nonce import UsedNonce
from app.models.hospitals import Facility

logger = logging.getLogger(__name__)

# Maximum allowed clock skew in seconds (5 minutes)
MAX_CLOCK_SKEW_SECONDS = 300


class SystemIdentityContext:
    """
    Holds verified 3-Layer authentication & context attributes extracted from a signed request.
    """
    def __init__(
        self,
        system_code: str,
        key_id: str,
        user_id: Optional[str],
        user_role: Optional[str],
        facility_code: Optional[str],
        facility_name: Optional[str] = None,
        facility: Optional[Facility] = None
    ):
        self.system_code = system_code
        self.key_id = key_id
        self.user_id = user_id or "ANONYMOUS_SYSTEM"
        self.user_role = (user_role or "SYSTEM").upper()
        self.facility_code = facility_code
        self.facility_name = facility_name
        self.facility = facility


async def verify_crypto_request_signature(
    request: Request,
    db: Session = Depends(get_db)
) -> SystemIdentityContext:
    """
    FastAPI dependency that enforces RSA-2048 Cryptographic System Authentication & Replay Protection.
    Verifies X-System-Code, X-Key-ID, X-Signature-Timestamp, X-Request-Nonce, X-System-Signature.
    """
    headers = request.headers
    system_code = headers.get("X-System-Code") or headers.get("x-system-code")
    key_id = headers.get("X-Key-ID") or headers.get("x-key-id")
    timestamp_str = headers.get("X-Signature-Timestamp") or headers.get("x-signature-timestamp")
    nonce = headers.get("X-Request-Nonce") or headers.get("x-request-nonce")
    signature_b64 = headers.get("X-System-Signature") or headers.get("x-system-signature")

    # Optional 3-layer context headers passed from Central HIS
    user_id = headers.get("X-User-ID") or headers.get("x-user-id")
    user_role = headers.get("X-User-Role") or headers.get("x-user-role")
    facility_code = headers.get("X-Facility-Code") or headers.get("x-facility-code")
    facility_name = headers.get("X-Facility-Name") or headers.get("x-facility-name")

    if not all([system_code, timestamp_str, nonce, signature_b64]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required cryptographic authentication headers (X-System-Code, X-Signature-Timestamp, X-Request-Nonce, X-System-Signature)."
        )

    # 1. Replay Protection: Timestamp check
    try:
        req_timestamp = int(timestamp_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Signature-Timestamp header format."
        )

    current_timestamp = int(time.time())
    if abs(current_timestamp - req_timestamp) > MAX_CLOCK_SKEW_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Cryptographic signature expired or timestamp out of bounds (skew: {abs(current_timestamp - req_timestamp)}s)."
        )

    # 2. Replay Protection: Nonce check
    existing_nonce = db.query(UsedNonce).filter(
        UsedNonce.system_code == system_code,
        UsedNonce.nonce == nonce
    ).first()

    print(f"DEBUG: system_code={system_code}, nonce={nonce}, found={existing_nonce}")

    if existing_nonce:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Replay attack detected: X-Request-Nonce has already been processed."
        )

    # Record nonce immediately
    try:
        new_nonce_obj = UsedNonce(system_code=system_code, nonce=nonce)
        db.add(new_nonce_obj)
        db.commit()
        print(f"DEBUG: Saved nonce {new_nonce_obj.id}")
    except Exception as e:
        db.rollback()
        print(f"DEBUG: Nonce exception: {e}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Replay attack detected: X-Request-Nonce has already been processed."
        )




    # 3. Fetch Registered System Credential (Public Key)
    system_cred = db.query(SystemCredential).filter(
        SystemCredential.system_code == system_code,
        SystemCredential.status == "ACTIVE"
    ).first()

    if not system_cred or not system_cred.public_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unrecognized or revoked system code '{system_code}'."
        )

    # 4. Construct Signature Payload String
    body_bytes = await request.body()
    body_sha256 = hashlib.sha256(body_bytes).hexdigest()
    path = request.url.path

    signing_str = f"{request.method.upper()}\n{path}\n{system_code}\n{key_id or ''}\n{req_timestamp}\n{nonce}\n{body_sha256}"

    # 5. RSA Signature Verification
    try:
        public_key_obj = load_pem_public_key(system_cred.public_key.encode('utf-8'))
        raw_signature = base64.b64decode(signature_b64)

        public_key_obj.verify(
            raw_signature,
            signing_str.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
    except InvalidSignature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cryptographic system signature."
        )
    except Exception as e:
        logger.error(f"Error during signature verification: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Failed to verify system signature: {str(e)}"
        )

    # Update system_credential last_used_at
    try:
        system_cred.last_used_at = datetime.now(timezone.utc)
        db.commit()
    except Exception:
        db.rollback()

    # Resolve Facility ORM model — local facility-side systems (e.g. mock_hospitals) may
    # provision their own facility codes that don't match the central registry's, so fall
    # back to matching by name when the code lookup misses.
    facility = None
    if facility_code:
        facility = db.query(Facility).filter(Facility.facility_code.ilike(facility_code)).first()
    if not facility and facility_name:
        facility = db.query(Facility).filter(Facility.facility_name.ilike(facility_name)).first()

    return SystemIdentityContext(
        system_code=system_code,
        key_id=key_id or system_cred.key_id,
        user_id=user_id,
        user_role=user_role,
        facility_code=facility_code,
        facility_name=facility_name,
        facility=facility
    )
