"""
Pre-session admin auth endpoints: raw-key login probe and TOTP enrollment/verification.

Deliberately NOT gated by verify_admin_key (app.utils.security) — these are the
endpoints that establish a session in the first place, so the dependency they'd
be checked against doesn't apply yet. Once /2fa/verify succeeds, the panel gets
a signed session token and every other /api/v1/admin/* route (app.routers.admin,
gated by verify_admin_key) accepts that token instead of the raw key.
"""

from datetime import datetime, timezone

import pyotp
from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.admin import Admin
from app.models.api_key import APIKey
from app.schemas.admin_schema import (
    Admin2FASetupResponse,
    Admin2FAVerifyRequest,
    Admin2FAVerifyResponse,
    AdminLoginRequest,
    AdminLoginResponse,
)
from app.utils.rate_limit import limiter
from app.utils.security import (
    api_key_header,
    create_admin_session_token,
    generate_totp_secret,
    hash_api_key,
    resolve_admin_by_raw_key,
    settings,
    verify_totp,
)

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Auth"])


def _require_admin_from_header(api_key: str, db: Session) -> Admin:
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Admin API Key. Header 'X-API-Key' is required."
        )
    admin = resolve_admin_by_raw_key(db, api_key)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive Admin API Key. Access denied."
        )
    return admin


@router.post("/login", response_model=AdminLoginResponse, summary="Phase 1: validate a raw admin key")
@limiter.limit("20/minute")
def admin_login(request: Request, payload: AdminLoginRequest, db: Session = Depends(get_db)) -> AdminLoginResponse:
    """Tells the panel what to render next: root bypass, TOTP enrollment, or a code prompt."""
    api_key = payload.api_key.strip()
    incoming_hash = hash_api_key(api_key)

    # Root break-glass key skips 2FA entirely (see verify_admin_key).
    if api_key == settings.API_KEY or incoming_hash == hash_api_key(settings.API_KEY):
        return AdminLoginResponse(admin_name="ROOT", totp_enabled=False, needs_setup=False, root=True)

    admin = resolve_admin_by_raw_key(db, api_key)
    if admin:
        return AdminLoginResponse(
            admin_name=admin.name,
            totp_enabled=admin.totp_enabled,
            needs_setup=not admin.totp_secret,
        )

    hosp_key = db.query(APIKey).filter(
        (APIKey.api_key == incoming_hash) | (APIKey.api_key == api_key),
        APIKey.is_active == True
    ).first()
    if hosp_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden. '{hosp_key.hospital_name}' is a hospital credential, not an administrator account."
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or inactive Admin API Key. Access denied."
    )


@router.post("/2fa/setup", response_model=Admin2FASetupResponse, summary="Phase 2a: generate a TOTP secret to enroll")
@limiter.limit("10/minute")
def admin_2fa_setup(
    request: Request,
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Admin2FASetupResponse:
    """First-time enrollment only — a QR code the caller scans into Google Authenticator."""
    admin = _require_admin_from_header(api_key, db)
    if admin.totp_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "2FA is already enabled for this account.")

    secret = generate_totp_secret()
    admin.totp_secret = secret
    db.commit()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=admin.name, issuer_name="IRDSS Admin Console")
    return Admin2FASetupResponse(admin_name=admin.name, provisioning_uri=uri, secret=secret)


@router.post("/2fa/verify", response_model=Admin2FAVerifyResponse, summary="Phase 2b: confirm a TOTP code and issue a session token")
@limiter.limit("10/minute")
def admin_2fa_verify(
    request: Request,
    payload: Admin2FAVerifyRequest,
    api_key: str = Security(api_key_header),
    db: Session = Depends(get_db),
) -> Admin2FAVerifyResponse:
    """Used both to confirm first-time enrollment and for every regular login afterward."""
    admin = _require_admin_from_header(api_key, db)
    if not admin.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Call /admin/2fa/setup first to generate a secret.")

    if not verify_totp(admin.totp_secret, payload.code.strip()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired authentication code.")

    admin.totp_enabled = True
    admin.last_login_at = datetime.now(timezone.utc)
    db.commit()

    token = create_admin_session_token(admin.name)
    return Admin2FAVerifyResponse(token=token, admin_name=admin.name, totp_enabled=True)
