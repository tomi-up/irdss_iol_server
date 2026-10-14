from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.hospitals import Facility
from app.models.facility_capability import FacilityCapability
from app.models.api_key import APIKey
from app.schemas.hospital_schema import (
    FHIRHospitalLocationRequest,
    HospitalResourceResponse,
    HospitalDetailSchema
)
from app.utils.security import verify_api_key
from app.utils.three_layer_auth import enforce_three_layer_auth, ThreeLayerAuthContext

router = APIRouter(
    prefix="/api/v1/hospitals",
    tags=["Facility Management"]
)


class FacilityCapabilitySyncPayload(BaseModel):
    """Mirrors mock_hospitals' local `service_assessments` table field-for-field, so
    the local Service Assessment form can be pushed here without any translation."""
    authorized_bed_capacity: int = 0
    functional_beds: int = 0
    has_icu: bool = False
    has_nicu: bool = False
    has_er_trauma: bool = False
    has_delivery_room: bool = False
    has_hemodialysis: bool = False
    has_blood_bank: bool = False
    has_ct_mri: bool = False
    has_cardiologist: bool = False
    has_obgyn: bool = False
    has_neurologist: bool = False
    has_general_surgeon: bool = False


@router.put("/capability", summary="Upsert this facility's bed/capability profile from its local Service Assessment")
async def upsert_facility_capability(
    payload: FacilityCapabilitySyncPayload,
    db: Session = Depends(get_db),
    auth_ctx: ThreeLayerAuthContext = Depends(enforce_three_layer_auth)
):
    """
    Keeps PostgreSQL's FacilityCapability row (read by the AI referral-matching engine
    and the admin dashboard's bed-count stat) in sync with whatever a facility admin
    submits on mock_hospitals' local Service Assessment form -- previously that data
    never left MySQL, so a facility's real bed counts/capabilities had zero effect on
    its ranking in referral recommendations.
    """
    facility = auth_ctx.facility

    cap = db.query(FacilityCapability).filter(FacilityCapability.facility_id == facility.id).first()
    if not cap:
        cap = FacilityCapability(facility_id=facility.id)
        db.add(cap)

    for field_name in FacilityCapabilitySyncPayload.model_fields:
        setattr(cap, field_name, getattr(payload, field_name))

    db.commit()

    return {
        "status": "success",
        "message": f"Facility capability profile synced for '{facility.facility_name}'.",
        "facility_id": facility.id
    }


def extract_fhir_location_fields(payload: FHIRHospitalLocationRequest) -> dict:
    """
    Parses core facility identity and location from standard FHIR R4 Location resource.
    """
    data = {
        "facility_name": payload.name,
        "latitude": payload.position.latitude if payload.position else 0.0,
        "longitude": payload.position.longitude if payload.position else 0.0,
        "facility_type": "Level 1 Hospital",
    }

    if payload.extension:
        for ext in payload.extension:
            url = ext.url.lower()
            if ("facility_type" in url or "hospital_level" in url) and ext.valueString is not None:
                data["facility_type"] = ext.valueString

    return data


def enforce_facility_authorization(facility: Facility, auth_key: APIKey):
    """
    Strict access control check: Ensures that a facility API key can ONLY modify/view its own record.
    System administrators (SYSTEM_ADMIN) have full access.
    """
    if auth_key.hospital_name == "SYSTEM_ADMIN":
        return

    if facility.facility_name.strip().lower() != auth_key.hospital_name.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden. Your API Key belongs to '{auth_key.hospital_name}'. You are not authorized to view or modify records for '{facility.facility_name}'."
        )


@router.post(
    "/register",
    response_model=HospitalResourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new facility record (FHIR Location format)"
)
async def register_hospital_resource(
    payload: FHIRHospitalLocationRequest,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Registers a new facility resource record using FHIR R4 Location payload.
    Requires header: X-API-Key
    """
    try:
        extracted = extract_fhir_location_fields(payload)

        # Check permission: API key can only register under its own facility name
        if auth_key.hospital_name != "SYSTEM_ADMIN" and extracted["facility_name"].strip().lower() != auth_key.hospital_name.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden. Your API Key belongs to '{auth_key.hospital_name}'. You cannot register records for '{extracted['facility_name']}'."
            )

        existing = db.query(Facility).filter(
            Facility.facility_name.ilike(extracted["facility_name"])
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Facility '{extracted['facility_name']}' already exists with ID {existing.id}. Use PUT to update records."
            )

        new_facility = Facility(
            facility_name=extracted["facility_name"],
            facility_type=extracted["facility_type"],
            latitude=extracted["latitude"],
            longitude=extracted["longitude"],
            facility_status="Active"
        )

        db.add(new_facility)
        db.flush()
        new_facility.facility_code = f"FAC-{new_facility.id:06d}"

        # Create default capability row
        cap = FacilityCapability(facility_id=new_facility.id)
        db.add(cap)

        db.commit()
        db.refresh(new_facility)

        return HospitalResourceResponse(
            status="success",
            message="Facility resource record successfully registered.",
            hospital=HospitalDetailSchema.model_validate(new_facility)
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register facility record: {str(e)}"
        )


@router.put(
    "/{hospital_id}",
    response_model=HospitalResourceResponse,
    summary="Update facility record by ID (FHIR R4 Location format)"
)
async def update_hospital_fhir(
    hospital_id: int,
    payload: FHIRHospitalLocationRequest,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Updates an existing facility record using a FHIR R4 Location payload.
    Requires header: X-API-Key matching the target facility.
    """
    try:
        facility = db.query(Facility).filter(Facility.id == hospital_id).first()
        if not facility:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Facility record with ID {hospital_id} not found."
            )

        # Enforce multi-tenant security
        enforce_facility_authorization(facility, auth_key)

        extracted = extract_fhir_location_fields(payload)

        facility.facility_name = extracted["facility_name"]
        facility.facility_type = extracted["facility_type"]
        facility.latitude = extracted["latitude"]
        facility.longitude = extracted["longitude"]

        db.commit()
        db.refresh(facility)

        return HospitalResourceResponse(
            status="success",
            message=f"Facility record for '{facility.facility_name}' updated successfully.",
            hospital=HospitalDetailSchema.model_validate(facility)
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update facility record: {str(e)}"
        )


@router.get(
    "/{hospital_id}",
    response_model=HospitalDetailSchema,
    summary="Retrieve facility details by ID"
)
async def get_hospital_details(
    hospital_id: int,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Retrieves details for a specific facility.
    Requires header: X-API-Key matching the target facility.
    """
    facility = db.query(Facility).filter(Facility.id == hospital_id).first()
    if not facility:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Facility record with ID {hospital_id} not found."
        )

    # Enforce multi-tenant security
    enforce_facility_authorization(facility, auth_key)

    return HospitalDetailSchema.model_validate(facility)


@router.get(
    "",
    response_model=List[HospitalDetailSchema],
    summary="List all facilities (System Admin only or authenticated view)"
)
async def list_hospitals(
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Lists facility records.
    If authenticated as a specific facility, returns that facility's record.
    If authenticated as SYSTEM_ADMIN, returns all facility records.
    """
    if auth_key.hospital_name != "SYSTEM_ADMIN":
        facilities = db.query(Facility).filter(
            Facility.facility_name.ilike(auth_key.hospital_name)
        ).all()
    else:
        facilities = db.query(Facility).all()

    return [HospitalDetailSchema.model_validate(f) for f in facilities]
