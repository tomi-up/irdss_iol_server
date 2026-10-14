import logging
from typing import Optional
from fastapi import Request, HTTPException, Depends, status
from sqlalchemy import or_
from sqlalchemy.orm import Session
from app.database.db_connection import get_db
from app.utils.crypto_auth import verify_crypto_request_signature, SystemIdentityContext
from app.models.hospitals import Facility

logger = logging.getLogger(__name__)

class ThreeLayerAuthContext:
    """
    Holds fully verified 3-Layer Authorization context.
    """
    def __init__(self, system_ctx: SystemIdentityContext, facility: Facility):
        self.system = system_ctx
        self.user_id = system_ctx.user_id
        self.user_role = system_ctx.user_role
        self.facility = facility
        self.facility_id = facility.id
        self.facility_code = facility.facility_code


async def enforce_three_layer_auth(
    request: Request,
    db: Session = Depends(get_db),
    system_ctx: SystemIdentityContext = Depends(verify_crypto_request_signature)
) -> ThreeLayerAuthContext:
    """
    FastAPI dependency enforcing 3-Layer Authorization:
    1. Layer 1 (System): RSA Public Key signature verified against system_credentials.
    2. Layer 2 (User): Verified presence of user context (X-User-ID, X-User-Role).
    3. Layer 3 (Facility): Verified presence of X-Facility-Code and active facility status.
    """
    facility_code = system_ctx.facility_code
    if not facility_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required X-Facility-Code context header."
        )

    facility = system_ctx.facility or db.query(Facility).filter(Facility.facility_code.ilike(facility_code)).first()

    if not facility:
        # Fallback: match by code or name string, including the caller's own facility name
        # (mock_hospitals-style local systems provision facility codes that don't match ours)
        conditions = [Facility.facility_code.ilike(facility_code), Facility.facility_name.ilike(facility_code)]
        if system_ctx.facility_name:
            conditions.append(Facility.facility_name.ilike(system_ctx.facility_name))
        facility = db.query(Facility).filter(or_(*conditions)).first()

    if not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility '{facility_code}' is not registered in central IRDSS."
        )

    if facility.facility_status and facility.facility_status.upper() != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Facility '{facility.facility_name}' is currently {facility.facility_status.upper()}."
        )

    return ThreeLayerAuthContext(system_ctx=system_ctx, facility=facility)


def verify_object_facility_ownership(ctx: ThreeLayerAuthContext, target_facility_id: int, target_facility_code: Optional[str] = None):
    """
    Enforces Object-Level Authorization: ensures the caller's verified facility matches the target resource facility.
    Prevents Facility A from mutating Facility B's records.
    """
    if target_facility_id and target_facility_id != ctx.facility_id:
        logger.warning(f"Object-level authorization denied! User {ctx.user_id} of facility {ctx.facility_code} attempted to access resource of facility_id {target_facility_id}.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Resource belongs to facility ID {target_facility_id}, but request is authenticated for facility {ctx.facility_code}."
        )

    if target_facility_code and target_facility_code.upper() != ctx.facility_code.upper():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access denied: Resource belongs to facility {target_facility_code}, but request is authenticated for facility {ctx.facility_code}."
        )
