import hashlib
from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.hospitals import HospitalResources
from app.models.referral_model import Referral
from app.models.referral_response_model import ReferralResponse
# Import your schemas, database connections, and SQLAlchemy models
from app.schemas.encounter import ReferralRequestSchema, ReferralResponseSchema, IncomingReferralSchema,  ResponsePayloadSchema, IncomingReferralDetailsSchema
from app.models.patient_model import PatientRecords
from app.models.referral_model import Referral
from app.models.api_key import APIKey
from app.utils.security import aes_encrypt, aes_decrypt
from app.database.db_connection import get_db
from app.ai.routing_filter import get_qualified_broadcast_targets

router = APIRouter()

# Enforces that requests must send the API key in the 'X-API-Key' header
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_hospital(
    api_key: str = Security(API_KEY_HEADER),
    db: Session = Depends(get_db)
) -> str:
    """
    Security Dependency that dynamically hashes and validates the API key against PostgreSQL.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key is missing from headers (X-API-Key)."
        )

    # 1. Generate SHA-256 hash of the incoming plaintext key
    hashed_key_incoming = hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    # 2. Query your 'api_keys' table dynamically
    record = db.query(APIKey).filter(
        APIKey.api_key == hashed_key_incoming,
        APIKey.is_active == True
    ).first()

    # 3. Reject if the key doesn't exist or is deactivated
    if not record:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Invalid or deactivated API key."
        )

    # Return the verified hospital identity
    return record.hospital_name


@router.get("/api/v1/referral/incoming", response_model=list[IncomingReferralDetailsSchema])
def get_incoming_referrals(
        db: Session = Depends(get_db),
        current_hospital_name: str = Depends(get_current_hospital)  # Resolved from X-API-Key [cite: 138]
):
    rec_hospital = db.query(HospitalResources).filter(
        HospitalResources.hospital_name == current_hospital_name
    ).first()

    hospital_lat = rec_hospital.latitude if rec_hospital else None
    hospital_long = rec_hospital.longitude if rec_hospital else None
    # Relational Join: Joins referral_responses with referrals and patient_record on-the-fly [cite: 145, 164]
    results = (
        db.query(ReferralResponse,Referral)
        .join(Referral, ReferralResponse.referral_id == Referral.referral_id)
        .filter(
            ReferralResponse.hospital_name == current_hospital_name,
            ReferralResponse.response_status == "PENDING"  # [cite: 191]
        )
        .all()
    )

    formatted_responses = []
    for resp, ref in results:
        # Safe Decryption Guard: Decrypts if encrypted; falls back to raw string on error [cite: 87]
        try:
            readable_patient_id = aes_decrypt(ref.patient_id)
        except Exception:
            # If the database row is an unencrypted legacy test record, use it directly [cite: 87]
            readable_patient_id = ref.patient_id

        formatted_responses.append({
            # Transactional fields from ReferralResponse [cite: 164]
            "id": resp.id,
            "referral_id": resp.referral_id,
            "hospital_name": resp.hospital_name,
            "response_status": resp.response_status,
            "seen_at": resp.seen_at,
            "responded_at": resp.responded_at,

            # Clinical metadata resolved relationally (never persisted in responses table) [cite: 164]
            "referring_facility": ref.referring_facility,
            "disease_severity": ref.disease_severity,
            "patient_id": readable_patient_id,  # ◄── This now securely decrypted! [cite: 87]
            "patient_age": ref.patient.age,  # Eager-loaded from PatientRecords [cite: 164]
            "patient_gender": ref.patient.gender or "unknown",  # Read direct model column [cite: 164]
            "clinical_reason": ref.clinical_reason or "No reason provided",
            "patient_latitude": ref.patient.latitude,  # Origin [cite: 120, 164]
            "patient_longitude": ref.patient.longitude,  # Origin [cite: 120, 164]
            "hospital_latitude": hospital_lat,  # Destination [cite: 120]
            "hospital_longitude": hospital_long
        })

    return formatted_responses

@router.patch("/api/v1/referral/{referral_id}/respond")
async def respond_to_referral(
        referral_id: str,
        payload: ResponsePayloadSchema,
        db: Session = Depends(get_db),
        hospital_name: str = Depends(get_current_hospital)
):
    """
    Updates the facility's response status in the database to ACCEPTED or REDIRECTED,
    stamping audited clinical turnaround times [cite: 315, 316].
    """
    if payload.decision not in ["ACCEPTED", "REDIRECTED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid decision. Must be 'ACCEPTED' or 'REDIRECTED'."
        )

    # 1. Fetch the corresponding alert row from the response pool
    alert = db.query(ReferralResponse).filter(
        ReferralResponse.referral_id == referral_id,
        ReferralResponse.hospital_name == hospital_name
    ).first()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referral alert not found for this facility."
        )

    try:
        # 2. Update status and save compliance metrics [cite: 315, 316]
        alert.response_status = payload.decision
        alert.responded_at = datetime.now(timezone.utc)

        # If they opened the form details, stamp seen_at if not already stamped [cite: 562]
        if not alert.seen_at:
            alert.seen_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "status": "success",
            "message": f"Referral successfully updated to {payload.decision} by {hospital_name}.",
            "responded_at": alert.responded_at
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database update failed: {str(e)}"
        )
@router.post("/api/v1/referral/initiate", response_model=ReferralResponseSchema)
async def initiate_referral(
    payload: ReferralRequestSchema,
    db: Session = Depends(get_db),
    # This executes get_current_hospital first, resolving who is calling the API
    referring_hospital: str = Depends(get_current_hospital)
):
    """
    Receives the FHIR payload, splits the data, and logs the transaction.
    """
    try:
        # Step A: Encrypt the patient ID
        encrypted_fhir_id = aes_encrypt(payload.patient_record.id)

        # Step B: Calculate Patient Age
        birth_date = datetime.strptime(payload.patient_record.birthDate, "%Y-%m-%d")
        current_date = datetime.now()
        calculated_age = current_date.year - birth_date.year - (
                (current_date.month, current_date.day) < (birth_date.month, birth_date.day)
        )
        patient_gender = getattr(payload.patient_record, "gender", "unknown") or "unknown"
        clinical_reason = "No reason provided"
        if payload.reasonCode and len(payload.reasonCode) > 0:
            clinical_reason = payload.reasonCode[0].text

        # Step C: Extract localized AI constraints
        patient_salary = 0.0
        patient_severity = 0
        patient_lat = 0.0
        patient_long = 0.0

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

        # Step D: Patient Records Upsert (Update or Insert)
        existing_patient = db.query(PatientRecords).filter(PatientRecords.fhir_id == encrypted_fhir_id).first()

        if existing_patient:
            existing_patient.age = calculated_age
            existing_patient.salary = patient_salary
            existing_patient.severity = patient_severity
            existing_patient.latitude = patient_lat
            existing_patient.longitude = patient_long
            existing_patient.gender = patient_gender
        else:
            new_patient_record = PatientRecords(
                fhir_id=encrypted_fhir_id,
                age=calculated_age,
                salary=patient_salary,
                severity=patient_severity,
                latitude=patient_lat,
                longitude=patient_long,
                gender=patient_gender,
                fitness=1
            )
            db.add(new_patient_record)

        # Step E: Insert transactional log to 'referrals'
        new_referral = Referral(
            patient_id=encrypted_fhir_id,
            referring_facility=referring_hospital,  # Resolved dynamically from PostgreSQL!
            receiving_facility=None,                # Left NULL for the AI process
            disease_severity=str(patient_severity),
            clinical_reason=clinical_reason,
            status="CREATED",
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_referral)

        # Step F: Atomic Commit
        db.commit()
        db.refresh(new_referral)
        qualified_hospitals = get_qualified_broadcast_targets(db, patient_severity)
        for hospital in qualified_hospitals:
            if hospital.hospital_name == referring_hospital:
                continue
            pending_alert = ReferralResponse(
                referral_id=new_referral.referral_id,
                hospital_name=hospital.hospital_name,
                response_status="PENDING"
            )
            db.add(pending_alert)

        db.commit()
        broadcast_list = [h.hospital_name for h in qualified_hospitals]

        return ReferralResponseSchema(
            status="success",
            message="Referral securely verified, split, and logged in the central IoL queue.",
            referral_tracking_id=new_referral.referral_id,
            referral_id=new_referral.referral_id
        )


    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to process referral: {str(e)}")


@router.get("/api/v1/referral/{referral_id}/recommendations")
def get_baseline_recommendations(
    referral_id: str,
    db: Session = Depends(get_db)
):
    # 1. Grab all response records where the hospital clicked ACCEPT
    accepted_responses = db.query(ReferralResponse).filter(
        ReferralResponse.referral_id == referral_id,
        ReferralResponse.response_status == "ACCEPTED"
    ).all()

    # 2. If no one has accepted yet, return an empty list
    if not accepted_responses:
        return []

    # 3. Pull the hospital names that accepted
    accepted_hospital_names = [resp.hospital_name for resp in accepted_responses]

    # 4. Resolve their resources (coordinates, level, available beds)
    hospitals = db.query(HospitalResources).filter(
        HospitalResources.hospital_name.in_(accepted_hospital_names)
    ).all()

    # 5. Return the raw list to the frontend (Baseline placeholder!)
    # Since FCM is not implemented yet, we just return them sorted by available beds
    baseline_list = []
    for h in hospitals:
        baseline_list.append({
            "hospital_name": h.hospital_name,
            "hospital_level": h.hospital_level,
            "available_beds": h.available_beds,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "matching_degree": 1.0  # Placeholder matching score of 100%
        })

    # Sort by available beds descending as a simple temporary ranking rule
    baseline_list.sort(key=lambda x: x["available_beds"], reverse=True)
    return baseline_list