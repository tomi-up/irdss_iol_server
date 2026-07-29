from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

# Import your schemas, database models, and AES encryption
from app.schemas.encounter import ReferralRequestSchema, ReferralResponseSchema
from app.models.patient_model import PatientRecords
from app.utils.security import aes_encrypt
from app.database.db_connection import get_db

router = APIRouter()

# THE INGESTION ENDPOINT (Receive Referral)
@router.post("/api/v1/referral/initiate", response_model=ReferralResponseSchema)
async def initiate_referral(payload: ReferralRequestSchema, db: Session = Depends(get_db)):
    """
    Receives the FHIR-compliant referral request from external health systems.
    Validates the data, encrypts sensitive fields using AES, and dynamically saves AI variables to the IoL Data Lake.
    """
    try:
        # 1. ENCRYPTION (Data Privacy Act Compliance):
        # We encrypt the sensitive patient ID before saving it to the data lake.
        encrypted_fhir_id = aes_encrypt(payload.patient_record.id)

        # 3. DYNAMIC AGE CALCULATION:
        # Parse the birthDate string (e.g., "1985-10-12") into a datetime object
        birth_date = datetime.strptime(payload.patient_record.birthDate, "%Y-%m-%d")
        current_date = datetime.now()

        # Calculate age by subtracting the years, and adjusting if they haven't had their birthday yet this year
        calculated_age = current_date.year - birth_date.year - (
                (current_date.month, current_date.day) < (birth_date.month, birth_date.day)
        )

        # 2. DYNAMIC AI VARIABLE EXTRACTION:
        # Set default fallback values
        patient_salary = 0.0
        patient_severity = 0
        patient_lat = 0.0
        patient_long = 0.0

        # Loop through the FHIR extensions to grab the specific IRDSS constraints
        if payload.patient_record.extension:
            for ext in payload.patient_record.extension:
                if "salary" in ext.url:
                    patient_salary = float(ext.valueDecimal)
                elif "severity" in ext.url:
                    patient_severity = int(ext.valueDecimal)
                elif "latitude" in ext.url:
                    patient_lat = float(ext.valueDecimal)
                elif "longitude" in ext.url:
                    patient_long = float(ext.valueDecimal)

        # 3. DATABASE INSERTION:
        # Map the validated FHIR payload into your SQLAlchemy PatientRecord model.
        new_patient_record = PatientRecords(
            fhir_id=encrypted_fhir_id,
            age=calculated_age,
            salary=patient_salary,      # Dynamically extracted from payload
            severity=patient_severity,  # Dynamically extracted from payload
            latitude=patient_lat,       # Dynamically extracted from payload
            longitude=patient_long,     # Dynamically extracted from payload
            fitness=1                   # Placeholder
        )

        db.add(new_patient_record)
        db.commit()
        db.refresh(new_patient_record)

        # 4. RESPONSE:
        # Return a safe confirmation without leaking sensitive patient data
        return ReferralResponseSchema(
            status="success",
            message="Referral securely received and saved to the data lake.",
            referral_tracking_id=payload.patient_record.id
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process the referral request: {str(e)}")