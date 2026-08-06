import hashlib
from fastapi import APIRouter, Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models.hospitals import HospitalResources
from app.models.referral_model import Referral
from app.models.referral_response_model import ReferralResponse
# Import your schemas, database connections, and SQLAlchemy models
from app.schemas.encounter import ReferralRequestSchema, ReferralResponseSchema, IncomingReferralSchema,  ResponsePayloadSchema, IncomingReferralDetailsSchema, FinalizeReferralSchema
from app.models.patient_model import PatientRecords
from app.models.referral_model import Referral
from app.models.api_key import APIKey
from app.utils.security import aes_encrypt, aes_decrypt, hash_patient_code
from app.database.db_connection import get_db
from app.ai.routing_filter import get_qualified_broadcast_targets
from app.ai.fcm_matching import compute_compatibility_scores

router = APIRouter()

# Enforces that requests must send the API key in the 'X-API-Key' header
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_current_hospital(
    request: Request,
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

    # Publish the resolved identity so the monitoring middleware can attribute this request
    request.state.hospital_name = record.hospital_name

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

        # The sending hospital's own coordinates — distinct from hospital_lat/hospital_long
        # above, which are *our* (the receiving hospital's) coordinates used for the
        # transfer-distance calculation, not where the referral actually came from.
        referring_hospital = db.query(HospitalResources).filter(
            HospitalResources.hospital_name == ref.referring_facility
        ).first()

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
            "hospital_longitude": hospital_long,
            "referring_facility_latitude": referring_hospital.latitude if referring_hospital else None,
            "referring_facility_longitude": referring_hospital.longitude if referring_hospital else None,
        })

    return formatted_responses

@router.patch("/api/v1/referral/{referral_id}/seen")
def mark_referral_seen(
        referral_id: str,
        db: Session = Depends(get_db),
        hospital_name: str = Depends(get_current_hospital)
):
    """
    Stamps seen_at the first time a facility opens a pending referral's detail form,
    ahead of and independent from their Accept/Redirect decision [cite: 194, 203].
    """
    alert = db.query(ReferralResponse).filter(
        ReferralResponse.referral_id == referral_id,
        ReferralResponse.hospital_name == hospital_name
    ).first()

    if not alert:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Referral alert not found for this facility."
        )

    now = datetime.now(timezone.utc)

    if not alert.seen_at:
        alert.seen_at = now

    # Also stamp the master referral row the first time ANY candidate hospital opens it,
    # so clinical turnaround time can be audited from the referring facility's side too [cite: 5, 6].
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    if referral and not referral.seen_at:
        referral.seen_at = now
        if referral.status == "CREATED":
            referral.status = "SEEN"

    db.commit()

    return {
        "status": "success",
        "seen_at": alert.seen_at
    }


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

        # Step C.1: Derive an anonymized, non-reversible patient_code (SHA-256 of Full Name +
        # Birthdate + Sex) so the central IoL can track active-referral state network-wide
        # without ever persisting the patient's identity [cite: 13, 110, 184].
        given_name = payload.patient_record.name[0].given[0] if payload.patient_record.name and payload.patient_record.name[0].given else ""
        family_name = payload.patient_record.name[0].family if payload.patient_record.name else ""
        patient_code = hash_patient_code(given_name, family_name, payload.patient_record.birthDate, patient_gender)

        # Step C.2: Block a second active referral for the same patient anywhere in the network.
        candidate_referrals = db.query(Referral).filter(
            Referral.patient_code == patient_code,
            Referral.receiving_facility.is_(None)
        ).all()

        for candidate in candidate_referrals:
            candidate_responses = db.query(ReferralResponse).filter(
                ReferralResponse.referral_id == candidate.referral_id
            ).all()
            # A referral is no longer "active" once every broadcasted hospital has redirected it
            fully_redirected = bool(candidate_responses) and all(
                r.response_status == "REDIRECTED" for r in candidate_responses
            )

            if not fully_redirected:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"This patient already has an active referral (ID: {candidate.referral_id}) "
                           f"moving through the regional network. Wait for it to be finalized or "
                           f"redirected by every facility before submitting a new one."
                )

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
            patient_code=patient_code,              # Anonymized SHA-256 identity for network-wide active-referral tracking
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


    except HTTPException:
        db.rollback()
        raise
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

    # 5. Resolve the patient behind this referral so the FCM engine has
    # something to match the hospitals against (severity, coordinates, budget)
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    patient = referral.patient if referral else None

    if patient and hospitals:
        scores = compute_compatibility_scores(patient, hospitals)
    else:
        scores = {h.hospital_name: 1.0 / len(hospitals) if hospitals else 1.0 for h in hospitals}

    # 6. Build the ranked list, highest compatibility (u_j) first
    ranked_list = []
    for h in hospitals:
        ranked_list.append({
            "hospital_name": h.hospital_name,
            "hospital_level": h.hospital_level,
            "available_beds": h.available_beds,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "matching_degree": scores.get(h.hospital_name, 0.0)
        })

    ranked_list.sort(key=lambda x: x["matching_degree"], reverse=True)
    return ranked_list


def _compute_referral_status(referral: Referral, responses: list[ReferralResponse]) -> str:
    """
    Derives an aggregate lifecycle status for a referral from its per-hospital
    ReferralResponse rows, since ACCEPTED/REDIRECTED are only ever written onto
    the response rows, never onto the parent Referral.status.
    """
    if referral.status == "CANCELLED":
        return "CANCELLED"
    if any(r.response_status == "ACCEPTED" for r in responses):
        return "ACCEPTED"
    if responses and all(r.response_status == "REDIRECTED" for r in responses):
        return "REDIRECTED"
    if referral.seen_at or any(r.seen_at for r in responses):
        return "SEEN"
    return "PENDING"


@router.get("/api/v1/referral/mine")
def get_my_referrals(
    db: Session = Depends(get_db),
    referring_hospital: str = Depends(get_current_hospital)
):
    """
    Lists every referral initiated by the calling hospital, with an aggregate
    status and the full per-hospital seen/response timeline embedded, so the
    "My Referrals" page needs a single request.
    """
    referrals = (
        db.query(Referral)
        .filter(Referral.referring_facility.ilike(referring_hospital))
        .order_by(Referral.created_at.desc())
        .all()
    )

    if not referrals:
        return []

    referral_ids = [r.referral_id for r in referrals]
    all_responses = db.query(ReferralResponse).filter(
        ReferralResponse.referral_id.in_(referral_ids)
    ).all()

    responses_by_referral: dict[str, list[ReferralResponse]] = {}
    for resp in all_responses:
        responses_by_referral.setdefault(resp.referral_id, []).append(resp)

    results = []
    for ref in referrals:
        ref_responses = responses_by_referral.get(ref.referral_id, [])

        try:
            readable_patient_id = aes_decrypt(ref.patient_id)
        except Exception:
            readable_patient_id = ref.patient_id

        status_value = _compute_referral_status(ref, ref_responses)

        results.append({
            "referral_id": ref.referral_id,
            "patient_id": readable_patient_id,
            "disease_severity": ref.disease_severity,
            "clinical_reason": ref.clinical_reason or "No reason provided",
            "status": status_value,
            "cancellable": status_value not in ("ACCEPTED", "CANCELLED"),
            "created_at": ref.created_at,
            "seen_at": ref.seen_at,
            "responses": [
                {
                    "hospital_name": r.hospital_name,
                    "response_status": r.response_status,
                    "seen_at": r.seen_at,
                    "responded_at": r.responded_at,
                }
                for r in ref_responses
            ],
        })

    return results


@router.patch("/api/v1/referral/{referral_id}/cancel")
def cancel_referral(
    referral_id: str,
    db: Session = Depends(get_db),
    referring_hospital: str = Depends(get_current_hospital)
):
    """
    Lets the referring hospital cancel a referral it initiated, as long as no
    hospital has accepted it yet. Also flips any still-PENDING broadcast rows
    to CANCELLED so it drops off other hospitals' /incoming polling.
    """
    try:
        referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()

        if not referral:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found.")

        if referral.referring_facility.strip().lower() != referring_hospital.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only cancel referrals your own hospital initiated."
            )

        if referral.status == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This referral is already cancelled.")

        responses = db.query(ReferralResponse).filter(ReferralResponse.referral_id == referral_id).all()

        if any(r.response_status == "ACCEPTED" for r in responses):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This referral can no longer be cancelled because a hospital has already accepted it."
            )

        referral.status = "CANCELLED"
        for r in responses:
            if r.response_status == "PENDING":
                r.response_status = "CANCELLED"

        db.commit()

        return {
            "status": "success",
            "message": "Referral cancelled successfully.",
            "referral_id": referral_id
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to cancel referral: {str(e)}")


@router.patch("/api/v1/referral/{referral_id}/finalize")
def finalize_referral(
    referral_id: str,
    payload: FinalizeReferralSchema,
    db: Session = Depends(get_db),
    referring_hospital: str = Depends(get_current_hospital)
):
    """
    Lets the referring doctor lock in their chosen destination among the hospitals
    that accepted, closing the open referral session. Only a hospital that actually
    accepted can be finalized; every other accepting hospital is marked NOT_SELECTED,
    and the chosen hospital's daily PSO routing capacity is consumed at this point
    (not at Accept-click time), since only one of possibly several acceptances wins.
    """
    try:
        referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()

        if not referral:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found.")

        if referral.referring_facility.strip().lower() != referring_hospital.strip().lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only finalize referrals your own hospital initiated."
            )

        if referral.status == "CANCELLED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This referral has been cancelled.")

        if referral.receiving_facility:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"This referral has already been finalized to '{referral.receiving_facility}'."
            )

        responses = db.query(ReferralResponse).filter(ReferralResponse.referral_id == referral_id).all()
        chosen_response = next(
            (r for r in responses if r.hospital_name.strip().lower() == payload.hospital_name.strip().lower()
             and r.response_status == "ACCEPTED"),
            None
        )

        if not chosen_response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"'{payload.hospital_name}' has not accepted this referral and cannot be selected."
            )

        referral.receiving_facility = chosen_response.hospital_name
        referral.status = "ACCEPTED"

        for r in responses:
            if r.response_status == "ACCEPTED" and r.hospital_name != chosen_response.hospital_name:
                r.response_status = "NOT_SELECTED"

        chosen_hospital = db.query(HospitalResources).filter(
            HospitalResources.hospital_name.ilike(chosen_response.hospital_name)
        ).first()
        if chosen_hospital:
            chosen_hospital.referrals_accepted_today = (chosen_hospital.referrals_accepted_today or 0) + 1

        db.commit()

        return {
            "status": "success",
            "message": f"Referral finalized to '{chosen_response.hospital_name}'.",
            "referral_id": referral_id,
            "receiving_facility": chosen_response.hospital_name
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to finalize referral: {str(e)}")


@router.get("/api/v1/referral/outcomes")
def get_referral_outcomes(
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital)
):
    """
    For every referral this hospital's triage team clicked ACCEPT on, reports whether
    the referring clinic ultimately finalized the transfer to this hospital (CHOSEN) or
    picked a competitor instead (BYPASSED). Referrals still awaiting the referring
    clinic's final decision are omitted — they belong to neither bucket yet.
    """
    results = (
        db.query(ReferralResponse, Referral)
        .join(Referral, ReferralResponse.referral_id == Referral.referral_id)
        .filter(
            ReferralResponse.hospital_name == current_hospital_name,
            ReferralResponse.response_status.in_(["ACCEPTED", "NOT_SELECTED"])
        )
        .all()
    )

    outcomes = []
    for resp, ref in results:
        if resp.response_status == "NOT_SELECTED":
            outcome = "BYPASSED"
        elif ref.receiving_facility and ref.receiving_facility.strip().lower() == current_hospital_name.strip().lower():
            outcome = "CHOSEN"
        else:
            # Still ACCEPTED but not yet finalized by the referring clinic either way
            continue

        try:
            readable_patient_id = aes_decrypt(ref.patient_id)
        except Exception:
            readable_patient_id = ref.patient_id

        outcomes.append({
            "referral_id": ref.referral_id,
            "outcome": outcome,
            "referring_facility": ref.referring_facility,
            "receiving_facility": ref.receiving_facility,
            "patient_id": readable_patient_id,
            "patient_age": ref.patient.age if ref.patient else None,
            "patient_gender": (ref.patient.gender if ref.patient and ref.patient.gender else "unknown"),
            "disease_severity": ref.disease_severity,
            "clinical_reason": ref.clinical_reason or "No reason provided",
            "created_at": ref.created_at,
            "seen_at": resp.seen_at,
            "responded_at": resp.responded_at,
        })

    outcomes.sort(key=lambda o: o["created_at"] or "", reverse=True)
    return outcomes