from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.hospitals import HospitalResources
from app.models.api_key import APIKey
from app.schemas.hospital_schema import (
    FHIRHospitalLocationRequest,
    HospitalInventoryUpdatePayload,
    HospitalResourceResponse,
    HospitalDetailSchema
)
from app.utils.security import verify_api_key

router = APIRouter(
    prefix="/api/v1/hospitals",
    tags=["Hospital Inventory Management"]
)


def extract_fhir_location_fields(payload: FHIRHospitalLocationRequest) -> dict:
    """
    Parses dynamic IRDSS metrics from standard FHIR R4 Location resource extensions.
    """
    data = {
        "hospital_name": payload.name,
        "latitude": payload.position.latitude if payload.position else 0.0,
        "longitude": payload.position.longitude if payload.position else 0.0,
        "available_beds": 0,
        "emergency_equipment": False,
        "medical_equipment": False,
        "communication_systems": False,
        "medical_specialists_count": 0,
        "hospital_level": "Level 1",
        "hospital_environment": "Urban",
    }

    if payload.extension:
        for ext in payload.extension:
            url = ext.url.lower()
            if "hospital_level" in url and ext.valueString is not None:
                data["hospital_level"] = ext.valueString
            elif "hospital_environment" in url and ext.valueString is not None:
                data["hospital_environment"] = ext.valueString
            elif "available_beds" in url:
                if ext.valueInteger is not None:
                    data["available_beds"] = ext.valueInteger
                elif ext.valueDecimal is not None:
                    data["available_beds"] = int(ext.valueDecimal)
            elif "emergency_equipment" in url and ext.valueBoolean is not None:
                data["emergency_equipment"] = ext.valueBoolean
            elif "medical_equipment" in url and ext.valueBoolean is not None:
                data["medical_equipment"] = ext.valueBoolean
            elif "communication_systems" in url and ext.valueBoolean is not None:
                data["communication_systems"] = ext.valueBoolean
            elif "medical_specialists_count" in url:
                if ext.valueInteger is not None:
                    data["medical_specialists_count"] = ext.valueInteger
                elif ext.valueDecimal is not None:
                    data["medical_specialists_count"] = int(ext.valueDecimal)

    return data


def enforce_hospital_authorization(hospital: HospitalResources, auth_key: APIKey):
    """
    Strict access control check: Ensures that a hospital API key can ONLY modify/view its own inventory.
    System administrators (SYSTEM_ADMIN) have full access.
    """
    if auth_key.hospital_name == "SYSTEM_ADMIN":
        return

    if hospital.hospital_name.strip().lower() != auth_key.hospital_name.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden. Your API Key belongs to '{auth_key.hospital_name}'. You are not authorized to view or modify records for '{hospital.hospital_name}'."
        )


@router.get(
    "/me/inventory",
    response_model=HospitalDetailSchema,
    summary="Retrieve current hospital's inventory (Auto-identified by API Key)"
)
async def get_my_hospital_inventory(
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Automatically retrieves the inventory for the hospital associated with the provided API key.
    Requires header: X-API-Key
    """
    hospital = db.query(HospitalResources).filter(
        HospitalResources.hospital_name.ilike(auth_key.hospital_name)
    ).first()

    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No hospital record found for '{auth_key.hospital_name}'. Please register hospital resources first."
        )
    return HospitalDetailSchema.model_validate(hospital)


@router.patch(
    "/me/inventory",
    response_model=HospitalResourceResponse,
    summary="Quick patch update for current hospital's inventory (Auto-identified by API Key)"
)
async def patch_my_hospital_inventory(
    payload: HospitalInventoryUpdatePayload,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Allows a hospital to quickly update its own inventory metrics using its API key without needing a hospital ID in the URL.
    Requires header: X-API-Key
    """
    try:
        hospital = db.query(HospitalResources).filter(
            HospitalResources.hospital_name.ilike(auth_key.hospital_name)
        ).first()

        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No hospital record found for '{auth_key.hospital_name}'. Please register hospital resources first."
            )

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(hospital, field) and value is not None:
                setattr(hospital, field, value)

        db.commit()
        db.refresh(hospital)

        return HospitalResourceResponse(
            status="success",
            message=f"Hospital inventory metrics updated for '{hospital.hospital_name}'.",
            hospital=HospitalDetailSchema.model_validate(hospital)
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to patch hospital inventory: {str(e)}"
        )


@router.post(
    "/register",
    response_model=HospitalResourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register new hospital resource record (FHIR Location format)"
)
async def register_hospital_resource(
    payload: FHIRHospitalLocationRequest,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Registers a new hospital resource record using FHIR R4 Location payload.
    Requires header: X-API-Key
    """
    try:
        extracted = extract_fhir_location_fields(payload)

        # Check permission: Hospital key can only register under its own hospital name
        if auth_key.hospital_name != "SYSTEM_ADMIN" and extracted["hospital_name"].strip().lower() != auth_key.hospital_name.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden. Your API Key belongs to '{auth_key.hospital_name}'. You cannot register records for '{extracted['hospital_name']}'."
            )

        existing = db.query(HospitalResources).filter(
            HospitalResources.hospital_name.ilike(extracted["hospital_name"])
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Hospital '{extracted['hospital_name']}' already exists with ID {existing.id}. Use PUT or PATCH to update records."
            )

        new_hospital = HospitalResources(
            hospital_name=extracted["hospital_name"],
            hospital_level=extracted["hospital_level"],
            hospital_environment=extracted["hospital_environment"],
            latitude=extracted["latitude"],
            longitude=extracted["longitude"],
            available_beds=extracted["available_beds"],
            emergency_equipment=extracted["emergency_equipment"],
            medical_equipment=extracted["medical_equipment"],
            communication_systems=extracted["communication_systems"],
            medical_specialists_count=extracted["medical_specialists_count"]
        )

        db.add(new_hospital)
        db.commit()
        db.refresh(new_hospital)

        return HospitalResourceResponse(
            status="success",
            message="Hospital resource record successfully registered.",
            hospital=HospitalDetailSchema.model_validate(new_hospital)
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to register hospital record: {str(e)}"
        )


@router.put(
    "/{hospital_id}",
    response_model=HospitalResourceResponse,
    summary="Update hospital record by ID (FHIR R4 Location format)"
)
async def update_hospital_fhir(
    hospital_id: int,
    payload: FHIRHospitalLocationRequest,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Updates an existing hospital resource record using a FHIR R4 Location payload.
    Requires header: X-API-Key matching the target hospital.
    """
    try:
        hospital = db.query(HospitalResources).filter(HospitalResources.id == hospital_id).first()
        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hospital record with ID {hospital_id} not found."
            )

        # Enforce multi-tenant security
        enforce_hospital_authorization(hospital, auth_key)

        extracted = extract_fhir_location_fields(payload)

        hospital.hospital_name = extracted["hospital_name"]
        hospital.hospital_level = extracted["hospital_level"]
        hospital.hospital_environment = extracted["hospital_environment"]
        hospital.latitude = extracted["latitude"]
        hospital.longitude = extracted["longitude"]
        hospital.available_beds = extracted["available_beds"]
        hospital.emergency_equipment = extracted["emergency_equipment"]
        hospital.medical_equipment = extracted["medical_equipment"]
        hospital.communication_systems = extracted["communication_systems"]
        hospital.medical_specialists_count = extracted["medical_specialists_count"]

        db.commit()
        db.refresh(hospital)

        return HospitalResourceResponse(
            status="success",
            message=f"Hospital inventory for '{hospital.hospital_name}' updated successfully.",
            hospital=HospitalDetailSchema.model_validate(hospital)
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update hospital inventory: {str(e)}"
        )


@router.patch(
    "/{hospital_id}/inventory",
    response_model=HospitalResourceResponse,
    summary="Quick patch update for hospital inventory by ID"
)
async def patch_hospital_inventory(
    hospital_id: int,
    payload: HospitalInventoryUpdatePayload,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Allows quick updates to specific inventory metrics (beds, equipment status, specialist counts).
    Requires header: X-API-Key matching the target hospital.
    """
    try:
        hospital = db.query(HospitalResources).filter(HospitalResources.id == hospital_id).first()
        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hospital record with ID {hospital_id} not found."
            )

        # Enforce multi-tenant security
        enforce_hospital_authorization(hospital, auth_key)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if hasattr(hospital, field) and value is not None:
                setattr(hospital, field, value)

        db.commit()
        db.refresh(hospital)

        return HospitalResourceResponse(
            status="success",
            message=f"Hospital inventory metrics updated for '{hospital.hospital_name}'.",
            hospital=HospitalDetailSchema.model_validate(hospital)
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to patch hospital inventory: {str(e)}"
        )


@router.get(
    "/{hospital_id}",
    response_model=HospitalDetailSchema,
    summary="Retrieve hospital details by ID"
)
async def get_hospital_details(
    hospital_id: int,
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Retrieves inventory resource details for a specific hospital.
    Requires header: X-API-Key matching the target hospital.
    """
    hospital = db.query(HospitalResources).filter(HospitalResources.id == hospital_id).first()
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Hospital record with ID {hospital_id} not found."
        )

    # Enforce multi-tenant security
    enforce_hospital_authorization(hospital, auth_key)

    return HospitalDetailSchema.model_validate(hospital)


@router.get(
    "",
    response_model=List[HospitalDetailSchema],
    summary="List all hospitals (System Admin only or authenticated view)"
)
async def list_hospitals(
    db: Session = Depends(get_db),
    auth_key: APIKey = Depends(verify_api_key)
):
    """
    Lists hospital resource inventory records.
    If authenticated as a specific hospital, returns that hospital's record.
    If authenticated as SYSTEM_ADMIN, returns all hospital records.
    """
    if auth_key.hospital_name != "SYSTEM_ADMIN":
        hospitals = db.query(HospitalResources).filter(
            HospitalResources.hospital_name.ilike(auth_key.hospital_name)
        ).all()
    else:
        hospitals = db.query(HospitalResources).all()

    return [HospitalDetailSchema.model_validate(h) for h in hospitals]
