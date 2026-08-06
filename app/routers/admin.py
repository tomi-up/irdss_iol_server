"""
IRDSS Admin Panel API (/api/v1/admin).

Every route in this module is gated by `verify_admin_key`, which accepts only the
environment root key or an active SYSTEM_ADMIN credential. These are the only
endpoints in the gateway that intentionally read across tenant boundaries.
"""

import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.database.db_connection import engine, get_db
from app.models.api_key import APIKey
from app.models.hospitals import HospitalResources
from app.models.patient_model import PatientRecords
from app.models.referral_model import Referral
from app.models.referral_response_model import ReferralResponse
from app.routers.referral import _compute_referral_status
from app.schemas.admin_schema import (
    ActionResponse,
    AdminApiKeyCreate,
    AdminApiKeyIssuedResponse,
    AdminApiKeyItem,
    AdminApiKeyUpdate,
    AdminHospitalCreate,
    AdminHospitalItem,
    AdminHospitalUpdate,
    AdminIdentitySchema,
    AdminReferralDetail,
    AdminReferralItem,
    AdminReferralListResponse,
    AdminReferralResponseRow,
    AdminStatsResponse,
    DailyVolumeItem,
    LogEntrySchema,
    LogListResponse,
    StatusCountItem,
    SystemHealthResponse,
)
from app.utils.request_log import (
    MAX_LOG_ENTRIES,
    SERVER_STARTED_AT,
    clear_request_logs,
    get_request_logs,
    get_traffic_summary,
    get_uptime_seconds,
)
from app.utils.security import aes_decrypt, generate_irdss_api_key, verify_admin_key

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Admin Panel"],
    dependencies=[Depends(verify_admin_key)]
)


def _safe_decrypt(value: Optional[str]) -> str:
    """Decrypts an AES-encrypted patient identifier, falling back to the raw value on failure."""
    if not value:
        return ""
    try:
        return aes_decrypt(value)
    except Exception:
        return value


def _serialize_api_key(record: APIKey) -> AdminApiKeyItem:
    """Maps an APIKey ORM row onto its safe, secret-free admin representation."""
    return AdminApiKeyItem(
        id=record.id,
        hospital_name=record.hospital_name,
        api_key_display=record.api_key_display or "—",
        is_active=bool(record.is_active),
        created_at=record.created_at,
    )


def _build_referral_item(
    referral: Referral,
    responses: list[ReferralResponse],
    patient: Optional[PatientRecords]
) -> AdminReferralItem:
    """Assembles one admin referral table row from its referral, responses, and patient records."""
    return AdminReferralItem(
        referral_id=referral.referral_id,
        patient_id=_safe_decrypt(referral.patient_id),
        patient_age=patient.age if patient else None,
        patient_gender=patient.gender if patient else None,
        referring_facility=referral.referring_facility,
        receiving_facility=referral.receiving_facility,
        disease_severity=referral.disease_severity,
        clinical_reason=referral.clinical_reason,
        status=_compute_referral_status(referral, responses),
        broadcast_count=len(responses),
        accepted_count=len([r for r in responses if r.response_status == "ACCEPTED"]),
        created_at=referral.created_at,
        seen_at=referral.seen_at,
        evaluated_at=referral.evaluated_at,
    )


# IDENTITY


@router.get("/me", response_model=AdminIdentitySchema, summary="Validate the supplied admin key")
def get_admin_identity(admin: str = Depends(verify_admin_key)) -> AdminIdentitySchema:
    """Lightweight probe the admin panel calls on login to confirm a pasted key is valid."""
    return AdminIdentitySchema(
        hospital_name=admin,
        is_admin=True,
        server_time=datetime.now(timezone.utc),
    )


# DASHBOARD STATISTICS


@router.get("/stats", response_model=AdminStatsResponse, summary="Network-wide KPI snapshot")
def get_admin_stats(db: Session = Depends(get_db)) -> AdminStatsResponse:
    """Aggregates referral volume, lifecycle mix, and facility/key counts for the admin dashboard."""
    try:
        referrals = db.query(Referral).all()
        all_responses = db.query(ReferralResponse).all()

        responses_by_referral: dict[str, list[ReferralResponse]] = {}
        for resp in all_responses:
            responses_by_referral.setdefault(resp.referral_id, []).append(resp)

        now = datetime.now(timezone.utc)
        today = now.date()
        week_ago = now - timedelta(days=7)

        status_counter: Counter = Counter()
        severity_counter: Counter = Counter()
        referring_counter: Counter = Counter()
        receiving_counter: Counter = Counter()
        daily_counter: Counter = Counter()

        referrals_today = 0
        referrals_last_7_days = 0
        turnaround_minutes: list[float] = []

        for ref in referrals:
            ref_responses = responses_by_referral.get(ref.referral_id, [])
            computed_status = _compute_referral_status(ref, ref_responses)

            status_counter[computed_status] += 1
            severity_counter[ref.disease_severity or "Unspecified"] += 1
            referring_counter[ref.referring_facility] += 1
            if ref.receiving_facility:
                receiving_counter[ref.receiving_facility] += 1

            created = ref.created_at
            if created is not None:
                # Referral.created_at is stored naive-UTC; normalize before comparing.
                created_aware = created if created.tzinfo else created.replace(tzinfo=timezone.utc)
                if created_aware.date() == today:
                    referrals_today += 1
                if created_aware >= week_ago:
                    referrals_last_7_days += 1
                    daily_counter[created_aware.date().isoformat()] += 1

                responded = [r.responded_at for r in ref_responses if r.responded_at]
                if responded:
                    first = min(responded)
                    first_aware = first if first.tzinfo else first.replace(tzinfo=timezone.utc)
                    delta = (first_aware - created_aware).total_seconds() / 60.0
                    if delta >= 0:
                        turnaround_minutes.append(delta)

        # Fill the 7-day series so the chart never has holes.
        daily_volume = []
        for offset in range(6, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            daily_volume.append(DailyVolumeItem(date=day, count=daily_counter.get(day, 0)))

        hospitals = db.query(HospitalResources).all()
        total_keys = db.query(func.count(APIKey.id)).scalar() or 0
        active_keys = db.query(func.count(APIKey.id)).filter(APIKey.is_active == True).scalar() or 0

        avg_response = round(sum(turnaround_minutes) / len(turnaround_minutes), 2) if turnaround_minutes else None

        return AdminStatsResponse(
            total_referrals=len(referrals),
            referrals_today=referrals_today,
            referrals_last_7_days=referrals_last_7_days,
            active_referrals=status_counter.get("PENDING", 0) + status_counter.get("SEEN", 0),
            completed_referrals=status_counter.get("ACCEPTED", 0),
            cancelled_referrals=status_counter.get("CANCELLED", 0),
            total_hospitals=len(hospitals),
            total_available_beds=sum((h.available_beds or 0) for h in hospitals),
            total_api_keys=total_keys,
            active_api_keys=active_keys,
            avg_response_minutes=avg_response,
            status_breakdown=[StatusCountItem(label=k, count=v) for k, v in status_counter.most_common()],
            severity_breakdown=[StatusCountItem(label=k, count=v) for k, v in severity_counter.most_common()],
            top_referring_facilities=[StatusCountItem(label=k, count=v) for k, v in referring_counter.most_common(5)],
            top_receiving_facilities=[StatusCountItem(label=k, count=v) for k, v in receiving_counter.most_common(5)],
            daily_volume=daily_volume,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to compute admin statistics: {str(e)}"
        )


# REFERRAL OVERSIGHT


@router.get("/referrals", response_model=AdminReferralListResponse, summary="List every referral in the network")
def list_all_referrals(
    db: Session = Depends(get_db),
    status_filter: Optional[str] = Query(None, alias="status", description="PENDING/SEEN/ACCEPTED/REDIRECTED/CANCELLED"),
    facility: Optional[str] = Query(None, description="Matches either the referring or receiving facility"),
    severity: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Substring match on referral ID or clinical reason"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
) -> AdminReferralListResponse:
    """Returns a paginated, filterable view of all referrals regardless of owning facility."""
    try:
        query = db.query(Referral)

        if facility:
            like = f"%{facility.strip()}%"
            query = query.filter(or_(
                Referral.referring_facility.ilike(like),
                Referral.receiving_facility.ilike(like),
            ))

        if severity:
            query = query.filter(Referral.disease_severity.ilike(f"%{severity.strip()}%"))

        if search:
            like = f"%{search.strip()}%"
            query = query.filter(or_(
                Referral.referral_id.ilike(like),
                Referral.clinical_reason.ilike(like),
            ))

        referrals = query.order_by(Referral.created_at.desc()).all()

        referral_ids = [r.referral_id for r in referrals]
        responses_by_referral: dict[str, list[ReferralResponse]] = {}
        if referral_ids:
            for resp in db.query(ReferralResponse).filter(ReferralResponse.referral_id.in_(referral_ids)).all():
                responses_by_referral.setdefault(resp.referral_id, []).append(resp)

        items = [
            _build_referral_item(ref, responses_by_referral.get(ref.referral_id, []), ref.patient)
            for ref in referrals
        ]

        # Status is derived from response rows, so it must be filtered after assembly.
        if status_filter:
            wanted = status_filter.strip().upper()
            items = [i for i in items if i.status == wanted]

        total = len(items)
        start = (page - 1) * page_size
        return AdminReferralListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=items[start:start + page_size],
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list referrals: {str(e)}"
        )


@router.get("/referrals/{referral_id}", response_model=AdminReferralDetail, summary="Full referral audit trail")
def get_referral_detail(referral_id: str, db: Session = Depends(get_db)) -> AdminReferralDetail:
    """Returns one referral with its patient context and the complete per-hospital response timeline."""
    referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
    if not referral:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Referral '{referral_id}' not found."
        )

    responses = db.query(ReferralResponse).filter(
        ReferralResponse.referral_id == referral_id
    ).order_by(ReferralResponse.id.asc()).all()

    patient = referral.patient
    base = _build_referral_item(referral, responses, patient)

    return AdminReferralDetail(
        **base.model_dump(),
        patient_severity=patient.severity if patient else None,
        patient_latitude=patient.latitude if patient else None,
        patient_longitude=patient.longitude if patient else None,
        responses=[AdminReferralResponseRow.model_validate(r) for r in responses],
    )


@router.patch("/referrals/{referral_id}/cancel", response_model=ActionResponse, summary="Force-cancel a stuck referral")
def admin_cancel_referral(referral_id: str, db: Session = Depends(get_db)) -> ActionResponse:
    """Administratively closes a referral that is stuck open, without needing the referring hospital's key."""
    try:
        referral = db.query(Referral).filter(Referral.referral_id == referral_id).first()
        if not referral:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Referral '{referral_id}' not found."
            )

        if referral.status == "CANCELLED":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Referral '{referral_id}' is already cancelled."
            )

        referral.status = "CANCELLED"
        db.query(ReferralResponse).filter(
            ReferralResponse.referral_id == referral_id,
            ReferralResponse.response_status.in_(["PENDING", "SEEN"])
        ).update({"response_status": "CANCELLED"}, synchronize_session=False)

        db.commit()
        return ActionResponse(message=f"Referral '{referral_id}' was force-cancelled by the administrator.")

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel referral: {str(e)}"
        )


# HOSPITAL MANAGEMENT


@router.get("/hospitals", response_model=list[AdminHospitalItem], summary="List all hospital nodes")
def list_all_hospitals(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
) -> list[AdminHospitalItem]:
    """Returns every registered hospital resource record, flagged with whether it holds an active API key."""
    query = db.query(HospitalResources)
    if search:
        query = query.filter(HospitalResources.hospital_name.ilike(f"%{search.strip()}%"))

    hospitals = query.order_by(HospitalResources.hospital_name.asc()).all()

    keyed_names = {
        name.strip().lower()
        for (name,) in db.query(APIKey.hospital_name).filter(APIKey.is_active == True).all()
    }

    items = []
    for h in hospitals:
        item = AdminHospitalItem.model_validate(h)
        item.has_api_key = (h.hospital_name or "").strip().lower() in keyed_names
        items.append(item)
    return items


@router.post(
    "/hospitals",
    response_model=AdminHospitalItem,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new hospital node"
)
def create_hospital(payload: AdminHospitalCreate, db: Session = Depends(get_db)) -> AdminHospitalItem:
    """Provisions a new hospital resource record directly from the admin panel."""
    try:
        existing = db.query(HospitalResources).filter(
            HospitalResources.hospital_name.ilike(payload.hospital_name.strip())
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Hospital '{payload.hospital_name}' already exists (ID {existing.id})."
            )

        hospital = HospitalResources(
            **payload.model_dump(),
            referrals_accepted_today=0,
        )
        hospital.hospital_name = payload.hospital_name.strip()

        db.add(hospital)
        db.commit()
        db.refresh(hospital)

        return AdminHospitalItem.model_validate(hospital)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create hospital: {str(e)}"
        )


@router.patch("/hospitals/{hospital_id}", response_model=AdminHospitalItem, summary="Update a hospital node")
def update_hospital(
    hospital_id: int,
    payload: AdminHospitalUpdate,
    db: Session = Depends(get_db)
) -> AdminHospitalItem:
    """Applies a partial update to any hospital's resource record, bypassing tenant scoping."""
    try:
        hospital = db.query(HospitalResources).filter(HospitalResources.id == hospital_id).first()
        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hospital record with ID {hospital_id} not found."
            )

        update_data = payload.model_dump(exclude_unset=True)

        new_name = update_data.get("hospital_name")
        if new_name and new_name.strip().lower() != (hospital.hospital_name or "").strip().lower():
            clash = db.query(HospitalResources).filter(
                HospitalResources.hospital_name.ilike(new_name.strip()),
                HospitalResources.id != hospital_id
            ).first()
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Another hospital already uses the name '{new_name}'."
                )

        for field, value in update_data.items():
            if value is not None:
                setattr(hospital, field, value.strip() if field == "hospital_name" else value)

        db.commit()
        db.refresh(hospital)
        return AdminHospitalItem.model_validate(hospital)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update hospital: {str(e)}"
        )


@router.delete("/hospitals/{hospital_id}", response_model=ActionResponse, summary="Remove a hospital node")
def delete_hospital(hospital_id: int, db: Session = Depends(get_db)) -> ActionResponse:
    """Deletes a hospital resource record, refusing while it still has referral history on file."""
    try:
        hospital = db.query(HospitalResources).filter(HospitalResources.id == hospital_id).first()
        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Hospital record with ID {hospital_id} not found."
            )

        name = hospital.hospital_name
        referral_count = db.query(func.count(Referral.referral_id)).filter(
            or_(Referral.referring_facility.ilike(name), Referral.receiving_facility.ilike(name))
        ).scalar() or 0

        if referral_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete '{name}': it is referenced by {referral_count} referral(s). "
                    "Deactivate its API key instead to take it offline."
                )
            )

        db.delete(hospital)
        db.commit()
        return ActionResponse(message=f"Hospital '{name}' was deleted.")

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete hospital: {str(e)}"
        )


# API KEY MANAGEMENT


@router.get("/api-keys", response_model=list[AdminApiKeyItem], summary="List issued API keys")
def list_api_keys(
    db: Session = Depends(get_db),
    search: Optional[str] = Query(None),
) -> list[AdminApiKeyItem]:
    """Lists every issued credential by owning hospital. Plaintext secrets are never returned."""
    query = db.query(APIKey)
    if search:
        query = query.filter(APIKey.hospital_name.ilike(f"%{search.strip()}%"))
    return [_serialize_api_key(k) for k in query.order_by(APIKey.id.asc()).all()]


@router.post(
    "/api-keys",
    response_model=AdminApiKeyIssuedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint a new API key"
)
def create_api_key(payload: AdminApiKeyCreate, db: Session = Depends(get_db)) -> AdminApiKeyIssuedResponse:
    """Generates a hospital credential, persists only its SHA-256 hash, and returns the plaintext once."""
    try:
        hospital_name = payload.hospital_name.strip()

        hospital = db.query(HospitalResources).filter(
            HospitalResources.hospital_name.ilike(hospital_name)
        ).first()
        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No hospital named '{hospital_name}' is registered. Add it under Hospitals first."
            )

        existing = db.query(APIKey).filter(
            APIKey.hospital_name.ilike(hospital.hospital_name),
            APIKey.is_active == True
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"'{hospital.hospital_name}' already holds an active key (ID {existing.id}). "
                    "Rotate that key instead of minting a duplicate."
                )
            )

        # Use the hospital's canonical stored name/casing, not whatever the caller typed,
        # so this row always matches HospitalResources.hospital_name exactly.
        raw_key, hashed_key, display_key = generate_irdss_api_key(hospital.hospital_name)
        record = APIKey(
            hospital_name=hospital.hospital_name,
            api_key=hashed_key,
            api_key_display=display_key,
            is_active=True
        )

        db.add(record)
        db.commit()
        db.refresh(record)

        return AdminApiKeyIssuedResponse(
            message=f"API key issued for '{hospital.hospital_name}'. Copy it now — it cannot be shown again.",
            raw_key=raw_key,
            key=_serialize_api_key(record),
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to issue API key: {str(e)}"
        )


@router.post(
    "/api-keys/{key_id}/rotate",
    response_model=AdminApiKeyIssuedResponse,
    summary="Rotate an existing API key"
)
def rotate_api_key(key_id: int, db: Session = Depends(get_db)) -> AdminApiKeyIssuedResponse:
    """Replaces a credential's secret in place, immediately invalidating the previous key."""
    try:
        record = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key with ID {key_id} not found."
            )

        raw_key, hashed_key, display_key = generate_irdss_api_key(record.hospital_name)
        record.api_key = hashed_key
        record.api_key_display = display_key
        record.is_active = True

        db.commit()
        db.refresh(record)

        return AdminApiKeyIssuedResponse(
            message=(
                f"Key rotated for '{record.hospital_name}'. The previous key is now invalid — "
                "update that hospital's HIS configuration."
            ),
            raw_key=raw_key,
            key=_serialize_api_key(record),
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rotate API key: {str(e)}"
        )


@router.patch("/api-keys/{key_id}", response_model=AdminApiKeyItem, summary="Activate/deactivate or reassign a key")
def update_api_key(key_id: int, payload: AdminApiKeyUpdate, db: Session = Depends(get_db)) -> AdminApiKeyItem:
    """Toggles a credential's active flag or reassigns its owning hospital without changing the secret."""
    try:
        record = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key with ID {key_id} not found."
            )

        update_data = payload.model_dump(exclude_unset=True)

        if "is_active" in update_data and update_data["is_active"] is not None:
            record.is_active = update_data["is_active"]

        if update_data.get("hospital_name"):
            record.hospital_name = update_data["hospital_name"].strip()

        db.commit()
        db.refresh(record)
        return _serialize_api_key(record)

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update API key: {str(e)}"
        )


@router.delete("/api-keys/{key_id}", response_model=ActionResponse, summary="Permanently revoke an API key")
def delete_api_key(key_id: int, db: Session = Depends(get_db)) -> ActionResponse:
    """Permanently deletes a credential row, hard-revoking the hospital node's gateway access."""
    try:
        record = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key with ID {key_id} not found."
            )

        owner = record.hospital_name
        db.delete(record)
        db.commit()
        return ActionResponse(message=f"API key for '{owner}' was permanently revoked.")

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke API key: {str(e)}"
        )


# SERVER MONITORING & LOGS


@router.get("/system/health", response_model=SystemHealthResponse, summary="Live gateway health snapshot")
def get_system_health(
    db: Session = Depends(get_db),
    window_minutes: int = Query(60, ge=1, le=1440),
) -> SystemHealthResponse:
    """Probes the PostgreSQL connection and folds in buffered traffic metrics and table row counts."""
    db_connected = True
    db_error: Optional[str] = None
    db_latency_ms: Optional[float] = None

    started = time.perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        db_latency_ms = round((time.perf_counter() - started) * 1000, 2)
    except Exception as e:
        db_connected = False
        db_error = str(e)

    table_counts: dict[str, int] = {}
    if db_connected:
        try:
            table_counts = {
                "referrals": db.query(func.count(Referral.referral_id)).scalar() or 0,
                "referral_responses": db.query(func.count(ReferralResponse.id)).scalar() or 0,
                "patient_record": db.query(func.count(PatientRecords.id)).scalar() or 0,
                "hospital_resources": db.query(func.count(HospitalResources.id)).scalar() or 0,
                "api_keys": db.query(func.count(APIKey.id)).scalar() or 0,
            }
        except Exception as e:
            db_error = f"Row counts unavailable: {str(e)}"

    traffic = get_traffic_summary(window_minutes=window_minutes)

    return SystemHealthResponse(
        status="healthy" if db_connected else "degraded",
        server_started_at=SERVER_STARTED_AT,
        uptime_seconds=round(get_uptime_seconds(), 2),
        database_connected=db_connected,
        database_error=db_error,
        database_latency_ms=db_latency_ms,
        table_counts=table_counts,
        **traffic,
    )


@router.get("/system/logs", response_model=LogListResponse, summary="Recent gateway request log")
def get_system_logs(
    level: Optional[str] = Query(None, description="INFO / WARNING / ERROR"),
    path: Optional[str] = Query(None, description="Substring match on the request path"),
    hospital: Optional[str] = Query(None, description="Substring match on the authenticated hospital"),
    limit: int = Query(200, ge=1, le=MAX_LOG_ENTRIES),
) -> LogListResponse:
    """Serves the in-memory HTTP request buffer, newest first, for the live log viewer."""
    entries = get_request_logs(
        level=level,
        path_contains=path,
        hospital_name=hospital,
        limit=limit,
    )
    return LogListResponse(
        buffered_entries=get_traffic_summary()["buffered_entries"],
        max_entries=MAX_LOG_ENTRIES,
        items=[LogEntrySchema(**entry) for entry in entries],
    )


@router.delete("/system/logs", response_model=ActionResponse, summary="Flush the in-memory log buffer")
def flush_system_logs() -> ActionResponse:
    """Clears the request ring buffer so the operator can watch a clean window of traffic."""
    discarded = clear_request_logs()
    return ActionResponse(message=f"Cleared {discarded} buffered log entr{'y' if discarded == 1 else 'ies'}.")
