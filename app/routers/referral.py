import hashlib
import os
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import unquote
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security, status
from fastapi.security import APIKeyHeader
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import date, datetime, time, timedelta, timezone

from app.models.hospitals import Facility, HospitalResources
from app.models.facility_capability import FacilityCapability

from app.models.referral_model import Referral
from app.models.referral_response_model import ReferralResponse
from app.models.referral_reason import ReferralReason
from app.models.referral_attachment import ReferralAttachment
# Import your schemas, database connections, and SQLAlchemy models
from app.schemas.encounter import ReferralRequestSchema, ReferralResponseSchema, IncomingReferralSchema,  ResponsePayloadSchema, IncomingReferralDetailsSchema, FinalizeReferralSchema, ArriveReferralSchema, DepartReferralSchema
from app.models.patient_model import PatientRecords
from app.models.referral_model import Referral
from app.models.api_key import APIKey
from app.utils.security import aes_encrypt, aes_decrypt, hash_patient_code
from app.database.db_connection import get_db
from app.ai.routing_filter import get_qualified_broadcast_targets
from app.ai.fcm_matching import compute_compatibility_scores
from app.utils.diagnosis_capability import derive_required_capabilities
from app.utils.ws_manager import manager

router = APIRouter()

ATTACHMENT_ROOT = Path(__file__).resolve().parents[2] / "storage" / "referral_attachments"
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
MAX_ATTACHMENTS_PER_STAGE = 5
ALLOWED_ATTACHMENT_TYPES = {
    "PHILHEALTH_MDR", "XRAY", "LAB_RESULT", "PRESCRIPTION",
    "DISCHARGE_SUMMARY", "CONSENT_FORM", "OTHER",
}
ALLOWED_STAGE_TYPES = {
    "REFERRAL": ALLOWED_ATTACHMENT_TYPES,
    "DEPARTURE": ALLOWED_ATTACHMENT_TYPES - {"PHILHEALTH_MDR"},
}


def _serialize_referral_reasons(db: Session, referral: Referral) -> list[dict]:
    rows = (
        db.query(ReferralReason)
        .filter(ReferralReason.referral_id == referral.referral_id)
        .order_by(ReferralReason.sort_order)
        .all()
    )
    if rows:
        return [
            {"code": row.code, "label": row.label, "is_primary": row.is_primary, "sort_order": row.sort_order}
            for row in rows
        ]
    if referral.clinical_reason:
        return [{"code": None, "label": referral.clinical_reason, "is_primary": True, "sort_order": 0}]
    return []


def _serialize_attachment(attachment: ReferralAttachment) -> dict:
    return {
        "id": attachment.id,
        "attachment_type": attachment.attachment_type,
        "workflow_stage": attachment.workflow_stage,
        "original_filename": attachment.original_filename,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "sha256": attachment.sha256,
        "uploaded_by_facility": attachment.uploaded_by_facility,
        "uploaded_by_user": attachment.uploaded_by_user,
        "created_at": attachment.created_at,
        "download_url": f"/api/v1/referral/{attachment.referral_id}/attachments/{attachment.id}",
    }


def _can_access_referral_files(referral: Referral, hospital_name: str) -> bool:
    caller = hospital_name.strip().casefold()
    return caller == referral.referring_facility.strip().casefold() or bool(
        referral.receiving_facility
        and caller == referral.receiving_facility.strip().casefold()
    )

# Enforces that requests must send the API key in the 'X-API-Key' header
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


from app.utils.crypto_auth import verify_crypto_request_signature, SystemIdentityContext

async def get_current_hospital(
    request: Request,
    api_key: str = Security(API_KEY_HEADER),
    db: Session = Depends(get_db)
) -> str:
    """
    Security Dependency supporting both Cryptographic RSA Request Signatures and legacy API keys.
    """
    headers = request.headers
    has_system_code = headers.get("X-System-Code") or headers.get("x-system-code")

    # 1. Cryptographic System Authentication (RSA 2048-bit Signature)
    if has_system_code:
        sys_ctx: SystemIdentityContext = await verify_crypto_request_signature(request, db)
        fac_code = sys_ctx.facility_code
        if not fac_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing X-Facility-Code context header."
            )

        facility = sys_ctx.facility or db.query(Facility).filter(
            (Facility.facility_code.ilike(fac_code)) | (Facility.facility_name.ilike(fac_code))
        ).first()

        if not facility:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Facility '{fac_code}' is not registered in central IRDSS."
            )

        request.state.hospital_name = facility.facility_name
        return facility.facility_name

    # 2. Legacy API Key Fallback
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication failed: Missing RSA System Signature or X-API-Key header."
        )

    hashed_key_incoming = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    record = db.query(APIKey).filter(
        APIKey.api_key == hashed_key_incoming,
        APIKey.is_active == True
    ).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Invalid or deactivated API key."
        )

    request.state.hospital_name = record.hospital_name
    return record.hospital_name



@router.post("/api/v1/ws-ticket")
async def issue_ws_ticket(
    current_hospital_name: str = Depends(get_current_hospital)
):
    """
    Issues a short-lived (60s), one-time ticket that authorizes a real-time
    WebSocket connection for this facility at /ws/referrals. Required because
    browser WebSocket clients cannot attach the RSA signature headers used by
    every other endpoint directly onto the connection handshake.
    """
    token = manager.issue_ticket(current_hospital_name, ttl_seconds=60)
    return {"ticket": token, "expires_in": 60}


@router.get("/api/v1/referral/incoming", response_model=list[IncomingReferralDetailsSchema])
def get_incoming_referrals(
        db: Session = Depends(get_db),
        current_hospital_name: str = Depends(get_current_hospital)  # Resolved from X-API-Key [cite: 138]
):
    rec_hospital = db.query(Facility).filter(
        Facility.facility_name == current_hospital_name
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
        referring_hospital = db.query(Facility).filter(
            Facility.facility_name == ref.referring_facility
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
            "created_at": ref.created_at,
            "referring_facility": ref.referring_facility,
            "disease_severity": ref.disease_severity,
            "patient_id": readable_patient_id,  # ◄── This now securely decrypted! [cite: 87]
            "patient_age": ref.patient.age,  # Eager-loaded from PatientRecords [cite: 164]
            "patient_age_months": ref.patient.age_months,
            "patient_age_days": ref.patient.age_days,
            "patient_gender": ref.patient.gender or "unknown",  # Read direct model column [cite: 164]
            "clinical_reason": ref.clinical_reason or "No reason provided",
            "referral_reasons": _serialize_referral_reasons(db, ref),
            "consent_status": ref.consent_status,
            "consent_method": ref.consent_method,
            "diagnosis": ref.diagnosis,
            "chief_complaint": ref.chief_complaint,
            "is_pwd": ref.is_pwd,
            "is_pregnant": ref.is_pregnant,
            "is_senior_citizen": ref.is_senior_citizen,
            "has_allergy": ref.has_allergy,
            "allergy_details": ref.allergy_details,
            "patient_latitude": ref.patient.latitude,  # Origin [cite: 120, 164]
            "patient_longitude": ref.patient.longitude,  # Origin [cite: 120, 164]
            "hospital_latitude": hospital_lat,  # Destination [cite: 120]
            "hospital_longitude": hospital_long,
            "referring_facility_latitude": referring_hospital.latitude if referring_hospital else None,
            "referring_facility_longitude": referring_hospital.longitude if referring_hospital else None,
        })

    return formatted_responses

@router.patch("/api/v1/referral/{referral_id}/seen")
async def mark_referral_seen(
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

    if referral:
        await manager.broadcast_to_facility(referral.referring_facility, {
            "type": "REFERRAL_SEEN",
            "referral_id": referral_id,
            "seen_by": hospital_name,
            "seen_at": alert.seen_at.isoformat() if alert.seen_at else None,
        })

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
        alert.redirect_reason_code = payload.redirect_reason_code
        alert.redirect_reason_text = payload.redirect_reason_text

        # If they opened the form details, stamp seen_at if not already stamped [cite: 562]
        if not alert.seen_at:
            alert.seen_at = datetime.now(timezone.utc)

        db.commit()

        referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
        if referral:
            await manager.broadcast_to_facility(referral.referring_facility, {
                "type": "REFERRAL_ACCEPTED" if payload.decision == "ACCEPTED" else "REFERRAL_REDIRECTED",
                "referral_id": referral_id,
                "hospital_name": hospital_name,
                "responded_at": alert.responded_at.isoformat() if alert.responded_at else None,
                "redirect_reason_code": alert.redirect_reason_code,
                "redirect_reason_text": alert.redirect_reason_text,
            })

        return {
            "status": "success",
            "message": f"Referral successfully updated to {payload.decision} by {hospital_name}.",
            "responded_at": alert.responded_at,
            "redirect_reason_code": alert.redirect_reason_code,
            "redirect_reason_text": alert.redirect_reason_text,
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
        # Precise age in whole months -- `calculated_age` alone floors to 0 for any infant
        # under a year, which isn't clinically useful on a triage alert (a newborn and an
        # 11-month-old would look identical)
        calculated_age_months = (
            (current_date.year - birth_date.year) * 12 + (current_date.month - birth_date.month)
            - (1 if current_date.day < birth_date.day else 0)
        )
        # Precise age in whole days -- `calculated_age_months` alone floors to 0 for any
        # newborn under a month old, so a 1-day-old and a 29-day-old would otherwise look
        # identical too (both show "0 months old")
        calculated_age_days = (current_date.date() - birth_date.date()).days
        patient_gender = getattr(payload.patient_record, "gender", "unknown") or "unknown"
        clinical_reason = "No reason provided"
        diagnosis_text = None
        referral_reason_values = []
        if payload.reasonCode and len(payload.reasonCode) > 0:
            clinical_reason = payload.reasonCode[0].text
            if payload.reasonCode[0].coding and len(payload.reasonCode[0].coding) > 0:
                diagnosis_text = payload.reasonCode[0].coding[0].display
            for index, reason in enumerate(payload.reasonCode):
                reason_code = None
                if reason.coding and len(reason.coding) > 0:
                    reason_code = reason.coding[0].code
                referral_reason_values.append({
                    "code": reason_code,
                    "label": reason.text.strip(),
                    "is_primary": index == 0,
                    "sort_order": index,
                })

        # Step C: Extract localized AI constraints
        patient_salary = 0.0
        patient_severity = 0
        patient_lat = 0.0
        patient_long = 0.0
        chief_complaint = None
        patient_phone = None
        patient_address = None
        patient_civil_status = None
        patient_philhealth_number = None
        patient_philhealth_status = None
        vital_bp = None
        vital_hr = None
        vital_rr = None
        vital_temp_c = None
        vital_o2sat = None
        vital_height_cm = None
        vital_weight_kg = None
        is_pwd = False
        is_pregnant = False
        is_senior_citizen = False
        has_allergy = False
        allergy_details = None
        consent_status = None
        consent_method = None
        consent_text_version = None
        consent_recorded_at = None
        consent_witnessed_by = None
        consent_signer_type = None
        consent_signer_name = None
        consent_representative_relationship = None
        consent_document_sha256 = None

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
                elif "chiefComplaint" in ext.url:
                    chief_complaint = ext.valueString
                elif "diagnosis" in ext.url:
                    diagnosis_text = ext.valueString
                elif "phone" in ext.url:
                    patient_phone = ext.valueString
                elif "address" in ext.url:
                    patient_address = ext.valueString
                elif "civilStatus" in ext.url:
                    patient_civil_status = ext.valueString
                elif "philhealthNumber" in ext.url:
                    patient_philhealth_number = ext.valueString
                elif "philhealthStatus" in ext.url:
                    patient_philhealth_status = ext.valueString
                elif "vitalBloodPressure" in ext.url:
                    vital_bp = ext.valueString
                elif "vitalHeartRate" in ext.url:
                    vital_hr = str(int(ext.valueDecimal)) if ext.valueDecimal is not None else None
                elif "vitalRespiratoryRate" in ext.url:
                    vital_rr = str(int(ext.valueDecimal)) if ext.valueDecimal is not None else None
                elif "vitalTemperature" in ext.url:
                    vital_temp_c = str(ext.valueDecimal) if ext.valueDecimal is not None else None
                elif "vitalOxygenSaturation" in ext.url:
                    vital_o2sat = str(int(ext.valueDecimal)) if ext.valueDecimal is not None else None
                elif "vitalHeight" in ext.url:
                    vital_height_cm = str(ext.valueDecimal) if ext.valueDecimal is not None else None
                elif "vitalWeight" in ext.url:
                    vital_weight_kg = str(ext.valueDecimal) if ext.valueDecimal is not None else None
                elif "isPwd" in ext.url:
                    is_pwd = bool(ext.valueBoolean)
                elif "isPregnant" in ext.url:
                    is_pregnant = bool(ext.valueBoolean)
                elif "isSeniorCitizen" in ext.url:
                    is_senior_citizen = bool(ext.valueBoolean)
                elif "hasAllergy" in ext.url:
                    has_allergy = bool(ext.valueBoolean)
                elif "allergyDetails" in ext.url:
                    allergy_details = ext.valueString
                elif "consentStatus" in ext.url:
                    consent_status = ext.valueString
                elif "consentMethod" in ext.url:
                    consent_method = ext.valueString
                elif "consentTextVersion" in ext.url:
                    consent_text_version = ext.valueString
                elif "consentRecordedAt" in ext.url:
                    try:
                        consent_recorded_at = datetime.fromisoformat((ext.valueString or "").replace("Z", "+00:00"))
                    except ValueError:
                        consent_recorded_at = None
                elif "consentWitnessedBy" in ext.url:
                    consent_witnessed_by = ext.valueString
                elif "consentSignerType" in ext.url:
                    consent_signer_type = ext.valueString
                elif "consentSignerName" in ext.url:
                    consent_signer_name = ext.valueString
                elif "consentRepresentativeRelationship" in ext.url:
                    consent_representative_relationship = ext.valueString
                elif "consentDocumentSha256" in ext.url:
                    consent_document_sha256 = ext.valueString

        if (
            (consent_status or "").strip().upper() != "GRANTED"
            or (consent_method or "").strip().upper() not in {"PAPER", "ELECTRONIC"}
            or (consent_text_version or "").strip() != "referral-consent-2026-09-v1"
            or consent_recorded_at is None
            or not (consent_witnessed_by or "").strip()
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Valid patient referral consent metadata is required.",
            )

        consent_status = consent_status.strip().upper()
        consent_method = consent_method.strip().upper()
        consent_text_version = consent_text_version.strip()[:50]
        consent_witnessed_by = consent_witnessed_by.strip()[:255]
        if consent_recorded_at.tzinfo is None:
            consent_recorded_at = consent_recorded_at.replace(tzinfo=timezone.utc)
        if consent_method == "ELECTRONIC" and abs((datetime.now(timezone.utc) - consent_recorded_at).total_seconds()) > 1800:
            raise HTTPException(status_code=422, detail="Electronic consent has expired. Please review and sign it again.")
        if consent_method == "ELECTRONIC":
            consent_signer_type = (consent_signer_type or "").strip().upper()
            consent_signer_name = (consent_signer_name or "").strip()
            consent_representative_relationship = (consent_representative_relationship or "").strip()
            consent_document_sha256 = (consent_document_sha256 or "").strip().lower()
            if consent_signer_type not in {"PATIENT", "PARENT_GUARDIAN", "AUTHORIZED_REPRESENTATIVE"}:
                raise HTTPException(status_code=422, detail="Electronic consent has an invalid signer type.")
            if not consent_signer_name or len(consent_signer_name) > 255:
                raise HTTPException(status_code=422, detail="Electronic consent requires the signer's full name.")
            if consent_signer_type != "PATIENT" and (
                not consent_representative_relationship or len(consent_representative_relationship) > 100
            ):
                raise HTTPException(status_code=422, detail="Electronic consent requires the representative relationship.")
            if len(consent_document_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in consent_document_sha256):
                raise HTTPException(status_code=422, detail="Electronic consent requires a valid SHA-256 document hash.")
        else:
            consent_signer_type = None
            consent_signer_name = None
            consent_representative_relationship = None
            consent_document_sha256 = None

        # Step C.0: Derive which specific facility capabilities (dialysis, OB delivery,
        # neurology, etc.) this diagnosis requires, on top of the baseline severity tier
        all_reason_text = " ".join(reason["label"] for reason in referral_reason_values)
        required_capabilities = derive_required_capabilities(diagnosis_text, chief_complaint, all_reason_text or clinical_reason)

        # Step C.1: Derive an anonymized, non-reversible patient_code (SHA-256 of Full Name +
        # Birthdate + Sex) so the central IoL can track active-referral state network-wide
        # without ever persisting the patient's identity [cite: 13, 110, 184].
        given_name = payload.patient_record.name[0].given[0] if payload.patient_record.name and payload.patient_record.name[0].given else ""
        family_name = payload.patient_record.name[0].family if payload.patient_record.name else ""
        patient_code = hash_patient_code(given_name, family_name, payload.patient_record.birthDate, patient_gender)

        # Step C.1b: Encrypt the patient's full identity for storage on this Referral row only --
        # never on PatientRecords. Only ever decrypted by the finalized receiving facility via
        # GET /api/v1/referral/{id}/patient-details.
        full_name = (payload.subject.display or f"{given_name} {family_name}".strip()) if payload.subject else f"{given_name} {family_name}".strip()
        if consent_method == "ELECTRONIC" and consent_signer_type == "PATIENT" and consent_signer_name.casefold() != full_name.casefold():
            raise HTTPException(status_code=422, detail="A patient signature must use the selected patient's full name.")
        encrypted_full_name = aes_encrypt(full_name) if full_name else None
        encrypted_dob = aes_encrypt(payload.patient_record.birthDate) if payload.patient_record.birthDate else None
        encrypted_phone = aes_encrypt(patient_phone) if patient_phone else None
        encrypted_address = aes_encrypt(patient_address) if patient_address else None
        encrypted_civil_status = aes_encrypt(patient_civil_status) if patient_civil_status else None
        encrypted_philhealth_number = aes_encrypt(patient_philhealth_number) if patient_philhealth_number else None
        encrypted_philhealth_status = aes_encrypt(patient_philhealth_status) if patient_philhealth_status else None
        encrypted_consent_signer_name = aes_encrypt(consent_signer_name) if consent_signer_name else None
        encrypted_consent_relationship = aes_encrypt(consent_representative_relationship) if consent_representative_relationship else None

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
            existing_patient.age_months = calculated_age_months
            existing_patient.age_days = calculated_age_days
            existing_patient.salary = patient_salary
            existing_patient.severity = patient_severity
            existing_patient.latitude = patient_lat
            existing_patient.longitude = patient_long
            existing_patient.gender = patient_gender
        else:
            new_patient_record = PatientRecords(
                fhir_id=encrypted_fhir_id,
                age=calculated_age,
                age_months=calculated_age_months,
                age_days=calculated_age_days,
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
            diagnosis=diagnosis_text,
            chief_complaint=chief_complaint,
            required_capability=",".join(required_capabilities) if required_capabilities else None,
            patient_full_name=encrypted_full_name,
            patient_dob=encrypted_dob,
            patient_phone=encrypted_phone,
            patient_address=encrypted_address,
            patient_civil_status=encrypted_civil_status,
            patient_philhealth_number=encrypted_philhealth_number,
            patient_philhealth_status=encrypted_philhealth_status,
            vital_bp=vital_bp,
            vital_hr=vital_hr,
            vital_rr=vital_rr,
            vital_temp_c=vital_temp_c,
            vital_o2sat=vital_o2sat,
            vital_height_cm=vital_height_cm,
            vital_weight_kg=vital_weight_kg,
            is_pwd=is_pwd,
            is_pregnant=is_pregnant,
            is_senior_citizen=is_senior_citizen,
            has_allergy=has_allergy,
            allergy_details=allergy_details,
            consent_status=consent_status,
            consent_method=consent_method,
            consent_text_version=consent_text_version,
            consent_recorded_at=consent_recorded_at,
            consent_witnessed_by=consent_witnessed_by,
            consent_signer_type=consent_signer_type,
            consent_signer_name=encrypted_consent_signer_name,
            consent_representative_relationship=encrypted_consent_relationship,
            consent_document_sha256=consent_document_sha256,
            status="CREATED",
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_referral)
        db.flush()
        for reason in referral_reason_values:
            db.add(ReferralReason(referral_id=new_referral.referral_id, **reason))

        # Step F: Atomic Commit
        db.commit()
        db.refresh(new_referral)
        qualified_hospitals = get_qualified_broadcast_targets(db, patient_severity, required_capabilities)
        for hospital in qualified_hospitals:
            if hospital.facility_name == referring_hospital:
                continue
            pending_alert = ReferralResponse(
                referral_id=new_referral.referral_id,
                hospital_name=hospital.facility_name,
                response_status="PENDING"
            )
            db.add(pending_alert)

        db.commit()
        broadcast_list = [h.facility_name for h in qualified_hospitals]

        for hospital_name in broadcast_list:
            if hospital_name.strip().lower() == referring_hospital.strip().lower():
                continue
            await manager.broadcast_to_facility(hospital_name, {
                "type": "NEW_REFERRAL",
                "referral_id": new_referral.referral_id,
                "referring_facility": referring_hospital,
                "disease_severity": patient_severity,
                "created_at": new_referral.created_at.isoformat() if new_referral.created_at else None,
            })

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
    hospitals = db.query(Facility).filter(
        Facility.facility_name.in_(accepted_hospital_names)
    ).all()

    # 5. Resolve the patient behind this referral so the FCM engine has
    # something to match the hospitals against (severity, coordinates, budget)
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    patient = referral.patient if referral else None

    # 5b. Bed counts live on FacilityCapability, not Facility -- no ORM relationship
    # links them, so resolve it with an explicit lookup keyed by facility_id, and stamp
    # it onto each Facility instance so fcm_matching's bed_gap term reads real data
    # instead of silently defaulting to 0 (getattr(facility, 'functional_beds', 0))
    capability_by_facility_id = {
        c.facility_id: c for c in db.query(FacilityCapability).filter(
            FacilityCapability.facility_id.in_([h.id for h in hospitals])
        ).all()
    } if hospitals else {}
    for h in hospitals:
        h.functional_beds = capability_by_facility_id[h.id].functional_beds if h.id in capability_by_facility_id else 0

    if patient and hospitals:
        scores = compute_compatibility_scores(patient, hospitals)
    else:
        scores = {h.facility_name: 1.0 / len(hospitals) if hospitals else 1.0 for h in hospitals}

    # 6. Build the ranked list, highest compatibility (u_j) first
    ranked_list = []
    for h in hospitals:
        capability = capability_by_facility_id.get(h.id)
        ranked_list.append({
            "hospital_name": h.facility_name,
            "hospital_level": h.facility_type,
            "available_beds": capability.functional_beds if capability else 0,
            "latitude": h.latitude,
            "longitude": h.longitude,
            "matching_degree": scores.get(h.facility_name, 0.0)
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
    # Departure is the terminal state of the receiving episode and must take
    # precedence over arrival. Previously every departed patient stayed ARRIVED
    # forever because arrived_at was checked first.
    if referral.departed_at:
        return (referral.departure_outcome or "DEPARTED").strip().upper()
    if referral.arrived_at:
        return "ARRIVED"
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

    # Detect if a patient who arrived at their receiving facility was later referred
    # onward again from there -- lets the ORIGINAL referring hospital see the patient's
    # journey continue past their own tracker instead of going dark after "Arrived".
    # Matched via patient_code, the same anonymized SHA-256 identity hash already used
    # to block a second concurrent active referral for the same patient network-wide.
    onward_by_source_referral: dict[str, dict] = {}
    own_referral_ids = {r.referral_id for r in referrals}
    arrived_patient_codes = [r.patient_code for r in referrals if r.arrived_at and r.patient_code]
    if arrived_patient_codes:
        candidate_onward = db.query(Referral).filter(
            Referral.patient_code.in_(arrived_patient_codes),
            Referral.referral_id.notin_(own_referral_ids)
        ).order_by(Referral.created_at.asc()).all()

        for ref in referrals:
            if not ref.arrived_at or not ref.patient_code:
                continue
            match = next(
                (c for c in candidate_onward
                 if c.patient_code == ref.patient_code
                 and ref.receiving_facility
                 and c.referring_facility.strip().lower() == ref.receiving_facility.strip().lower()
                 and c.created_at and c.created_at >= ref.arrived_at),
                None
            )
            if match:
                match_responses = db.query(ReferralResponse).filter(
                    ReferralResponse.referral_id == match.referral_id
                ).all()
                onward_by_source_referral[ref.referral_id] = {
                    "referral_id": match.referral_id,
                    "status": _compute_referral_status(match, match_responses),
                    "receiving_facility": match.receiving_facility,
                    "created_at": match.created_at,
                }

    results = []
    for ref in referrals:
        ref_responses = responses_by_referral.get(ref.referral_id, [])

        try:
            readable_patient_id = aes_decrypt(ref.patient_id)
        except Exception:
            readable_patient_id = ref.patient_id

        status_value = _compute_referral_status(ref, ref_responses)
        # A new referral created by the receiving hospital represents a distinct
        # onward transfer. The source referral remains linked to that new record,
        # but its display status should describe the outcome of this episode.
        if not ref.departed_at and onward_by_source_referral.get(ref.referral_id):
            status_value = "REFERRED_ONWARD"

        # The "Accepted" timeline step should reflect whichever response actually won --
        # the finalized hospital's acceptance if chosen, otherwise the first acceptance
        # in while the referring doctor still has to pick one
        accepted_at = None
        if ref.receiving_facility:
            chosen = next((r for r in ref_responses if r.hospital_name.strip().lower() == ref.receiving_facility.strip().lower()), None)
            accepted_at = chosen.responded_at if chosen else None
        else:
            first_accept = next((r for r in ref_responses if r.response_status == "ACCEPTED"), None)
            accepted_at = first_accept.responded_at if first_accept else None

        results.append({
            "referral_id": ref.referral_id,
            "patient_id": readable_patient_id,
            "disease_severity": ref.disease_severity,
            "clinical_reason": ref.clinical_reason or "No reason provided",
            "referral_reasons": _serialize_referral_reasons(db, ref),
            "consent_status": ref.consent_status,
            "consent_method": ref.consent_method,
            "consent_text_version": ref.consent_text_version,
            "consent_recorded_at": ref.consent_recorded_at,
            "consent_witnessed_by": ref.consent_witnessed_by,
            "status": status_value,
            "cancellable": status_value not in (
                "ACCEPTED", "ARRIVED", "CANCELLED", "DISCHARGED", "TRANSFERRED",
                "DECEASED", "LEFT_AMA", "DEPARTED", "REFERRED_ONWARD",
            ),
            "receiving_facility": ref.receiving_facility,
            "created_at": ref.created_at,
            "seen_at": ref.seen_at,
            "accepted_at": accepted_at,
            "finalized_at": ref.evaluated_at,
            "arrived_at": ref.arrived_at,
            "departed_at": ref.departed_at,
            "departure_outcome": ref.departure_outcome,
            "departure_remarks": ref.departure_remarks,
            "onward_referral": onward_by_source_referral.get(ref.referral_id),
            "responses": [
                {
                    "hospital_name": r.hospital_name,
                    "response_status": r.response_status,
                    "seen_at": r.seen_at,
                    "responded_at": r.responded_at,
                    "redirect_reason_code": r.redirect_reason_code,
                    "redirect_reason_text": r.redirect_reason_text,
                }
                for r in ref_responses
            ],
        })

    return results


@router.patch("/api/v1/referral/{referral_id}/cancel")
async def cancel_referral(
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

        for r in responses:
            await manager.broadcast_to_facility(r.hospital_name, {
                "type": "REFERRAL_CANCELLED",
                "referral_id": referral_id,
            })

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
async def finalize_referral(
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
        referral.evaluated_at = datetime.now(timezone.utc)

        # Close out every other hospital's alert once the decision is made -- not just
        # the ones that had ACCEPTED, but also any still-PENDING (never responded in
        # time). Otherwise a silent hospital would keep seeing this referral as an open
        # action item in /incoming forever, and the referring doctor's tracker would
        # show it stuck at "Pending" indefinitely even though the case is already closed.
        # REDIRECTED and CANCELLED are left alone -- those are real prior decisions.
        for r in responses:
            if r.hospital_name == chosen_response.hospital_name:
                continue
            if r.response_status in ("ACCEPTED", "PENDING"):
                r.response_status = "NOT_SELECTED"

        chosen_hospital = db.query(Facility).filter(
            Facility.facility_name.ilike(chosen_response.hospital_name)
        ).first()
        if chosen_hospital:
            chosen_hospital.referrals_accepted_today = (chosen_hospital.referrals_accepted_today or 0) + 1

        db.commit()

        # Real-time push: the chosen hospital gets a distinct "you won it" event, every
        # other hospital that had accepted (now flipped to NOT_SELECTED) is told to drop
        # this referral from its Incoming Patients view, and the referring hospital gets
        # a confirmation echo so a second open tab/session stays in sync too.
        await manager.broadcast_to_facility(chosen_response.hospital_name, {
            "type": "REFERRAL_FINALIZED_TO_YOU",
            "referral_id": referral_id,
            "referring_facility": referring_hospital,
        })

        for r in responses:
            if r.hospital_name != chosen_response.hospital_name and r.response_status == "NOT_SELECTED":
                await manager.broadcast_to_facility(r.hospital_name, {
                    "type": "REFERRAL_NOT_SELECTED",
                    "referral_id": referral_id,
                })

        await manager.broadcast_to_facility(referring_hospital, {
            "type": "REFERRAL_FINALIZED_CONFIRMED",
            "referral_id": referral_id,
            "receiving_facility": chosen_response.hospital_name,
        })

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


@router.get("/api/v1/referral/{referral_id}/patient-details")
def get_referral_patient_details(
    referral_id: str,
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital)
):
    """
    Reveals the patient's full identity (name, DOB, phone, address, civil status,
    PhilHealth info) -- but only to the facility this referral was actually finalized
    to. Every other facility, including ones that merely clicked Accept, gets a 403.
    """
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()

    if not referral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found.")

    if not referral.receiving_facility or referral.receiving_facility.strip().lower() != current_hospital_name.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Full patient details are only available to the facility this referral was finalized to."
        )

    def safe_decrypt(value):
        if not value:
            return None
        try:
            return aes_decrypt(value)
        except Exception:
            return None

    return {
        "referral_id": referral.referral_id,
        "full_name": safe_decrypt(referral.patient_full_name),
        "date_of_birth": safe_decrypt(referral.patient_dob),
        "phone": safe_decrypt(referral.patient_phone),
        "address": safe_decrypt(referral.patient_address),
        "civil_status": safe_decrypt(referral.patient_civil_status),
        "philhealth_number": safe_decrypt(referral.patient_philhealth_number),
        "philhealth_status": safe_decrypt(referral.patient_philhealth_status),
        "gender": referral.patient.gender if referral.patient else None,
        "age": referral.patient.age if referral.patient else None,
        "age_months": referral.patient.age_months if referral.patient else None,
        "age_days": referral.patient.age_days if referral.patient else None,
        "diagnosis": referral.diagnosis,
        "chief_complaint": referral.chief_complaint,
        "reason_text": referral.clinical_reason,
        "referral_reasons": _serialize_referral_reasons(db, referral),
        "attachments": [
            _serialize_attachment(item)
            for item in (
                db.query(ReferralAttachment)
                .filter(ReferralAttachment.referral_id == referral_id)
                .order_by(ReferralAttachment.created_at)
                .all()
            )
        ],
        "disease_severity": referral.disease_severity,
        "referring_facility": referral.referring_facility,
        "vital_bp": referral.vital_bp,
        "vital_hr": referral.vital_hr,
        "vital_rr": referral.vital_rr,
        "vital_temp_c": referral.vital_temp_c,
        "vital_o2sat": referral.vital_o2sat,
        "vital_height_cm": referral.vital_height_cm,
        "vital_weight_kg": referral.vital_weight_kg,
        "arrival_vital_bp": referral.arrival_vital_bp,
        "arrival_vital_hr": referral.arrival_vital_hr,
        "arrival_vital_rr": referral.arrival_vital_rr,
        "arrival_vital_temp_c": referral.arrival_vital_temp_c,
        "arrival_vital_o2sat": referral.arrival_vital_o2sat,
        "arrived_at": referral.arrived_at,
        "is_pwd": referral.is_pwd,
        "is_pregnant": referral.is_pregnant,
        "is_senior_citizen": referral.is_senior_citizen,
        "has_allergy": referral.has_allergy,
        "allergy_details": referral.allergy_details,
        "consent_status": referral.consent_status,
        "consent_method": referral.consent_method,
        "consent_text_version": referral.consent_text_version,
        "consent_recorded_at": referral.consent_recorded_at,
        "consent_witnessed_by": referral.consent_witnessed_by,
        "consent_signer_type": referral.consent_signer_type,
        "consent_signer_name": safe_decrypt(referral.consent_signer_name),
        "consent_representative_relationship": safe_decrypt(referral.consent_representative_relationship),
        "consent_document_sha256": referral.consent_document_sha256,
    }


@router.post("/api/v1/referral/{referral_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_referral_attachment(
    referral_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital),
):
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found.")

    workflow_stage = (request.headers.get("X-Workflow-Stage") or "").strip().upper()
    attachment_type = (request.headers.get("X-Attachment-Type") or "").strip().upper()
    encoded_filename = request.headers.get("X-Original-Filename") or "attachment"
    original_filename = os.path.basename(unquote(encoded_filename).replace("\\", "/")).strip()[:255]
    original_filename = "".join(ch for ch in original_filename if ch.isprintable() and ch not in "\r\n")

    if workflow_stage not in ALLOWED_STAGE_TYPES:
        raise HTTPException(status_code=422, detail="X-Workflow-Stage must be REFERRAL or DEPARTURE.")
    if attachment_type not in ALLOWED_STAGE_TYPES[workflow_stage]:
        raise HTTPException(status_code=422, detail="Invalid attachment type for this workflow stage.")
    if not original_filename:
        raise HTTPException(status_code=422, detail="A valid original filename is required.")

    caller = current_hospital_name.strip().casefold()
    if workflow_stage == "REFERRAL":
        if caller != referral.referring_facility.strip().casefold():
            raise HTTPException(status_code=403, detail="Only the referring facility can upload referral attachments.")
    else:
        if not referral.receiving_facility or caller != referral.receiving_facility.strip().casefold():
            raise HTTPException(status_code=403, detail="Only the finalized receiving facility can upload departure attachments.")
        if not referral.arrived_at:
            raise HTTPException(status_code=409, detail="Departure attachments require an arrived patient.")

    count_filters = [
        ReferralAttachment.referral_id == referral_id,
        ReferralAttachment.workflow_stage == workflow_stage,
    ]
    if attachment_type == "CONSENT_FORM":
        count_filters.append(ReferralAttachment.attachment_type == "CONSENT_FORM")
        attachment_limit = 1
    else:
        count_filters.append(ReferralAttachment.attachment_type != "CONSENT_FORM")
        attachment_limit = MAX_ATTACHMENTS_PER_STAGE
    existing_count = (
        db.query(func.count(ReferralAttachment.id))
        .filter(*count_filters)
        .scalar()
    )
    if existing_count >= attachment_limit:
        limit_message = "Only one signed consent form is allowed." if attachment_type == "CONSENT_FORM" else f"A maximum of {MAX_ATTACHMENTS_PER_STAGE} clinical attachments is allowed per stage."
        raise HTTPException(status_code=409, detail=limit_message)

    contents = await request.body()
    if not contents:
        raise HTTPException(status_code=422, detail="Attachment file is empty.")
    if len(contents) > MAX_ATTACHMENT_BYTES:
        raise HTTPException(status_code=413, detail="Attachment exceeds the 5 MB limit.")

    detected = None
    if contents.startswith(b"%PDF-"):
        detected = ("application/pdf", ".pdf")
    elif contents.startswith(b"\x89PNG\r\n\x1a\n"):
        detected = ("image/png", ".png")
    elif contents.startswith(b"\xff\xd8\xff"):
        detected = ("image/jpeg", ".jpg")
    if not detected:
        raise HTTPException(status_code=415, detail="Only valid PDF, PNG, and JPEG files are accepted.")

    mime_type, extension = detected
    content_sha256 = hashlib.sha256(contents).hexdigest()
    if (
        attachment_type == "CONSENT_FORM"
        and referral.consent_method == "ELECTRONIC"
        and referral.consent_document_sha256
        and content_sha256 != referral.consent_document_sha256
    ):
        raise HTTPException(status_code=422, detail="Electronic consent document hash does not match the recorded consent.")
    attachment_id = str(uuid.uuid4())
    stored_filename = f"{attachment_id}{extension}"
    referral_dir = ATTACHMENT_ROOT / referral_id
    referral_dir.mkdir(parents=True, exist_ok=True)
    full_path = referral_dir / stored_filename

    try:
        full_path.write_bytes(contents)
        attachment = ReferralAttachment(
            id=attachment_id,
            referral_id=referral_id,
            attachment_type=attachment_type,
            workflow_stage=workflow_stage,
            original_filename=original_filename,
            stored_filename=stored_filename,
            mime_type=mime_type,
            size_bytes=len(contents),
            sha256=content_sha256,
            uploaded_by_facility=current_hospital_name,
            uploaded_by_user=request.headers.get("X-User-ID"),
        )
        db.add(attachment)
        db.commit()
        db.refresh(attachment)
        return _serialize_attachment(attachment)
    except Exception:
        db.rollback()
        full_path.unlink(missing_ok=True)
        raise


@router.get("/api/v1/referral/{referral_id}/attachments")
def list_referral_attachments(
    referral_id: str,
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital),
):
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found.")
    if not _can_access_referral_files(referral, current_hospital_name):
        raise HTTPException(status_code=403, detail="Your facility cannot access these attachments.")

    attachments = (
        db.query(ReferralAttachment)
        .filter(ReferralAttachment.referral_id == referral_id)
        .order_by(ReferralAttachment.created_at)
        .all()
    )
    return [_serialize_attachment(item) for item in attachments]


@router.get("/api/v1/referral/{referral_id}/attachments/{attachment_id}")
def download_referral_attachment(
    referral_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital),
):
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    if not referral:
        raise HTTPException(status_code=404, detail="Referral not found.")
    if not _can_access_referral_files(referral, current_hospital_name):
        raise HTTPException(status_code=403, detail="Your facility cannot access this attachment.")

    attachment = (
        db.query(ReferralAttachment)
        .filter(
            ReferralAttachment.id == attachment_id,
            ReferralAttachment.referral_id == referral_id,
        )
        .first()
    )
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found.")

    full_path = ATTACHMENT_ROOT / referral_id / attachment.stored_filename
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="Attachment file is missing from storage.")
    return FileResponse(full_path, media_type=attachment.mime_type, filename=attachment.original_filename)


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
            "referral_reasons": _serialize_referral_reasons(db, ref),
            "created_at": ref.created_at,
            "seen_at": resp.seen_at,
            "responded_at": resp.responded_at,
            "arrived_at": ref.arrived_at,
            "departed_at": ref.departed_at,
            "departure_outcome": ref.departure_outcome,
            "departure_remarks": ref.departure_remarks,
        })

    outcomes.sort(key=lambda o: o["created_at"] or "", reverse=True)
    return outcomes


@router.get("/api/v1/referral/analytics")
def get_facility_analytics(
    start_date: Optional[date] = Query(None, description="Inclusive referral creation date"),
    end_date: Optional[date] = Query(None, description="Inclusive referral creation date"),
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital)
):
    """
    Facility-admin-facing aggregates that the outcome counters on Incoming Patients
    don't cover: why this facility sends and receives referrals, who sends patients
    TO this facility, who this facility sends patients TO, and monthly
    referral volume in both directions. Outcome counters themselves (Transferred To
    Us / Discharged / Referred Onward / etc.) are intentionally NOT duplicated here --
    the frontend reuses /api/v1/referral/outcomes so the two views can never drift
    apart on those numbers.
    """
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="start_date must be on or before end_date."
        )

    name = current_hospital_name.strip()
    date_filters = []
    if start_date:
        date_filters.append(Referral.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        # Use an exclusive upper bound so all times on end_date are included.
        date_filters.append(Referral.created_at < datetime.combine(end_date + timedelta(days=1), time.min))

    def top_n(column, filter_condition, limit=10):
        rows = (
            db.query(column.label("label"), func.count(Referral.referral_id).label("count"))
            .filter(filter_condition, *date_filters, column.isnot(None), column != "")
            .group_by(column)
            .order_by(func.count(Referral.referral_id).desc())
            .limit(limit)
            .all()
        )
        return [{"label": r.label, "count": r.count} for r in rows]

    top_reasons = top_n(
        Referral.clinical_reason,
        func.lower(Referral.referring_facility) == name.lower()
    )
    top_incoming_reasons = top_n(
        Referral.clinical_reason,
        func.lower(Referral.receiving_facility) == name.lower()
    )
    top_senders = top_n(
        Referral.referring_facility,
        func.lower(Referral.receiving_facility) == name.lower()
    )
    top_receivers = top_n(
        Referral.receiving_facility,
        func.lower(Referral.referring_facility) == name.lower()
    )

    month = func.date_trunc("month", Referral.created_at)
    sent_rows = (
        db.query(month.label("month"), func.count(Referral.referral_id).label("count"))
        .filter(func.lower(Referral.referring_facility) == name.lower(), *date_filters)
        .group_by(month)
        .order_by(month)
        .all()
    )
    received_rows = (
        db.query(month.label("month"), func.count(Referral.referral_id).label("count"))
        .filter(func.lower(Referral.receiving_facility) == name.lower(), *date_filters)
        .group_by(month)
        .order_by(month)
        .all()
    )
    sent_by_month = {r.month.strftime("%Y-%m"): r.count for r in sent_rows}
    received_by_month = {r.month.strftime("%Y-%m"): r.count for r in received_rows}
    all_months = sorted(set(sent_by_month) | set(received_by_month))
    monthly_volume = [
        {"month": m, "sent": sent_by_month.get(m, 0), "received": received_by_month.get(m, 0)}
        for m in all_months
    ]

    return {
        "top_reasons": top_reasons,
        "top_incoming_reasons": top_incoming_reasons,
        "top_senders": top_senders,
        "top_receivers": top_receivers,
        "monthly_volume": monthly_volume,
        "period": {
            "start_date": start_date.isoformat() if start_date else None,
            "end_date": end_date.isoformat() if end_date else None,
        },
    }


@router.patch("/api/v1/referral/{referral_id}/arrive")
async def mark_referral_arrived(
    referral_id: str,
    payload: Optional[ArriveReferralSchema] = None,
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital)
):
    """
    Stamps arrived_at the moment the receiving facility confirms the patient has
    physically shown up -- distinct from finalize (an administrative choice) and from
    viewing patient details (which can happen before arrival). This is the trigger the
    receiving facility's local HIS uses to decide when to create its own local patient
    record for this transfer, so referrals that get finalized but never arrive don't
    clutter the local roster as if they were already under care.

    Optionally accepts a fresh set of vitals taken at arrival -- kept separate from
    the referring facility's vital_* readings since a patient's condition can change
    meaningfully during transport. Never required: marking arrival must not be blocked
    on filling in vitals.
    """
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()

    if not referral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found.")

    if not referral.receiving_facility or referral.receiving_facility.strip().lower() != current_hospital_name.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the facility this referral was finalized to can mark the patient as arrived."
        )

    if not referral.arrived_at:
        referral.arrived_at = datetime.now(timezone.utc)

        if payload:
            if payload.vital_bp:
                referral.arrival_vital_bp = payload.vital_bp
            if payload.vital_hr:
                referral.arrival_vital_hr = payload.vital_hr
            if payload.vital_rr:
                referral.arrival_vital_rr = payload.vital_rr
            if payload.vital_temp_c:
                referral.arrival_vital_temp_c = payload.vital_temp_c
            if payload.vital_o2sat:
                referral.arrival_vital_o2sat = payload.vital_o2sat

        db.commit()

        await manager.broadcast_to_facility(referral.referring_facility, {
            "type": "PATIENT_ARRIVED",
            "referral_id": referral.referral_id,
            "arrived_at": referral.arrived_at.isoformat(),
        })

    return {
        "status": "success",
        "referral_id": referral.referral_id,
        "arrived_at": referral.arrived_at
    }


@router.patch("/api/v1/referral/{referral_id}/depart")
async def mark_referral_departed(
    referral_id: str,
    payload: DepartReferralSchema,
    db: Session = Depends(get_db),
    current_hospital_name: str = Depends(get_current_hospital)
):
    """
    Marks the end of this facility's episode of care for the patient -- discharged,
    transferred onward, deceased, or left against medical advice -- so the original
    referring hospital's tracker doesn't go dark after "Arrived". Only the facility
    the patient actually arrived at can record this, and only once.
    """
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()

    if not referral:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found.")

    if not referral.receiving_facility or referral.receiving_facility.strip().lower() != current_hospital_name.strip().lower():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the facility this referral was finalized to can record the patient's departure."
        )

    if not referral.arrived_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This patient hasn't been marked as arrived yet."
        )

    if referral.departed_at:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This patient's departure was already recorded ({referral.departure_outcome})."
        )

    referral.departed_at = datetime.now(timezone.utc)
    referral.departure_outcome = payload.outcome
    referral.departure_remarks = payload.remarks
    db.commit()

    await manager.broadcast_to_facility(referral.referring_facility, {
        "type": "PATIENT_DEPARTED",
        "referral_id": referral.referral_id,
        "departed_at": referral.departed_at.isoformat(),
        "departure_outcome": referral.departure_outcome,
    })

    return {
        "status": "success",
        "referral_id": referral.referral_id,
        "departed_at": referral.departed_at,
        "departure_outcome": referral.departure_outcome
    }
