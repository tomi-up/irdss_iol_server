from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.facility_user import FacilityUser
from app.models.hospitals import Facility
from app.utils.security import verify_password, create_facility_session_token

router = APIRouter(tags=["Facility Auth"])


class FacilityLoginRequest(BaseModel):
    username: str
    password: str


class FacilityLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    facility_id: int
    facility_code: str
    facility_name: str
    role: str


@router.post("/api/auth/login", response_model=FacilityLoginResponse)
def facility_login(payload: FacilityLoginRequest, db: Session = Depends(get_db)):
    """
    Facility staff authentication endpoint.
    Verifies credentials against facility_users table, updates last_login,
    and issues a signed JWT facility session token.
    """
    user = db.query(FacilityUser).filter(
        FacilityUser.username == payload.username.strip()
    ).first()

    if not user or user.status != "Active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password."
        )

    facility = db.query(Facility).filter(Facility.id == user.facility_id).first()
    if not facility:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Associated facility record not found."
        )

    # Update last_login timestamp
    user.last_login = datetime.now(timezone.utc)
    db.commit()

    token = create_facility_session_token(
        facility_id=facility.id,
        facility_code=facility.facility_code or f"FAC-{facility.id:06d}",
        facility_name=facility.facility_name,
        username=user.username,
        role=user.role
    )

    return FacilityLoginResponse(
        access_token=token,
        token_type="bearer",
        facility_id=facility.id,
        facility_code=facility.facility_code or f"FAC-{facility.id:06d}",
        facility_name=facility.facility_name,
        role=user.role
    )
