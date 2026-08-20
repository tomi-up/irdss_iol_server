"""
IRDSS Admin Panel API (/api/v1/admin).

Every route in this module is gated by `verify_admin_key`, which accepts only the
environment root key or an active SYSTEM_ADMIN credential. These are the only
endpoints in the gateway that intentionally read across tenant boundaries.
"""

import os
import time
import uuid
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.database.db_connection import engine, get_db
from app.models.api_key import APIKey
from app.models.hospitals import Facility, HospitalResources
from app.models.facility_capability import FacilityCapability
from app.models.facility_user import FacilityUser
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
    AdminFacilityCreate,
    AdminFacilityCredentialsCreate,
    AdminFacilityCredentialsIssuedResponse,
    AdminFacilityCredentialsItem,
    AdminFacilityItem,

    AdminFacilityUpdate,
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
from app.utils.security import (
    aes_decrypt,
    generate_irdss_api_key,
    get_password_hash,
    verify_admin_key,
)

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
        accepted_count=sum(1 for r in responses if r.response_status == "ACCEPTED"),
        created_at=referral.created_at,
        seen_at=min((r.seen_at for r in responses if r.seen_at), default=None),
        evaluated_at=min((r.responded_at for r in responses if r.responded_at), default=None),
    )


@router.get("/me", response_model=AdminIdentitySchema, summary="Validate admin authentication")
def get_admin_identity(request_identity: str = Depends(verify_admin_key)) -> AdminIdentitySchema:
    """Echoes back the caller's admin identity so the panel can confirm the token/key is valid."""
    return AdminIdentitySchema(
        hospital_name=request_identity,
        is_admin=True,
        server_time=datetime.now(timezone.utc),
    )


# DASHBOARD STATISTICS


@router.get("/stats", response_model=AdminStatsResponse, summary="Dashboard high-level metrics")
def get_admin_stats(db: Session = Depends(get_db)) -> AdminStatsResponse:
    """Computes network-wide referral volumes, response times, and facility totals."""
    try:
        now = datetime.now(timezone.utc)
        today = now.date()
        week_ago = now - timedelta(days=7)

        referrals = db.query(Referral).all()
        responses = db.query(ReferralResponse).all()

        responses_by_referral: dict[str, list[ReferralResponse]] = {}
        for r in responses:
            responses_by_referral.setdefault(r.referral_id, []).append(r)

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

        daily_volume = []
        for offset in range(6, -1, -1):
            day = (now - timedelta(days=offset)).date().isoformat()
            daily_volume.append(DailyVolumeItem(date=day, count=daily_counter.get(day, 0)))

        facilities = db.query(Facility).all()
        capabilities = db.query(FacilityCapability).all()
        total_beds = sum((c.functional_beds or 0) for c in capabilities)

        total_keys = db.query(func.count(APIKey.id)).scalar() or 0
        active_keys = db.query(func.count(APIKey.id)).filter(APIKey.is_active == True).scalar() or 0

        total_creds = db.query(func.count(FacilityUser.id)).scalar() or 0
        issued_creds = db.query(func.count(FacilityUser.id)).filter(FacilityUser.status == "Active").scalar() or 0

        avg_response = round(sum(turnaround_minutes) / len(turnaround_minutes), 2) if turnaround_minutes else None

        return AdminStatsResponse(
            total_referrals=len(referrals),
            referrals_today=referrals_today,
            referrals_last_7_days=referrals_last_7_days,
            active_referrals=status_counter.get("PENDING", 0) + status_counter.get("SEEN", 0),
            completed_referrals=status_counter.get("ACCEPTED", 0),
            cancelled_referrals=status_counter.get("CANCELLED", 0),
            total_hospitals=len(facilities),
            total_available_beds=total_beds,
            total_credentials=total_creds,
            issued_credentials=issued_creds,
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
            all_responses = db.query(ReferralResponse).filter(
                ReferralResponse.referral_id.in_(referral_ids)
            ).all()
            for resp in all_responses:
                responses_by_referral.setdefault(resp.referral_id, []).append(resp)

        items = []
        for ref in referrals:
            resp_list = responses_by_referral.get(ref.referral_id, [])
            computed_status = _compute_referral_status(ref, resp_list)

            if status_filter and computed_status != status_filter.upper():
                continue

            items.append(_build_referral_item(ref, resp_list, ref.patient))

        total = len(items)
        start = (page - 1) * page_size
        paged_items = items[start:start + page_size]

        return AdminReferralListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=paged_items,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch referral records: {str(e)}"
        )


@router.get("/referrals/{referral_id}", response_model=AdminReferralDetail, summary="Get full referral audit view")
def get_referral_detail(referral_id: str, db: Session = Depends(get_db)) -> AdminReferralDetail:
    """Returns detailed referral record including all candidate response timestamps."""
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


# FACILITY MANAGEMENT


@router.get("/facilities", response_model=list[AdminFacilityItem], summary="List all registered facilities")
def list_all_facilities(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
) -> list[AdminFacilityItem]:
    """Returns all registered health facility records, flagged with API key and login credential availability."""
    query = db.query(Facility)
    if search and isinstance(search, str):
        query = query.filter(Facility.facility_name.ilike(f"%{search.strip()}%"))


    facilities = query.order_by(Facility.facility_name.asc()).all()

    keyed_names = {
        name.strip().lower()
        for (name,) in db.query(APIKey.hospital_name).filter(APIKey.is_active == True).all()
    }

    facility_users_map = {
        fu.facility_id: fu.username
        for fu in db.query(FacilityUser).all()
    }

    items = []
    for f in facilities:
        item = AdminFacilityItem.model_validate(f)
        item.has_api_key = (f.facility_name or "").strip().lower() in keyed_names
        item.has_facility_user = f.id in facility_users_map
        item.facility_username = facility_users_map.get(f.id)
        items.append(item)
    return items


@router.post(
    "/facilities",
    response_model=AdminFacilityItem,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new facility"
)
async def create_facility(
    facility_name: str = Form(...),
    facility_type: str = Form("Level 1 Hospital"),
    ownership: str = Form("Government"),
    facility_head: Optional[str] = Form(None),
    region: Optional[str] = Form(None),
    province: Optional[str] = Form(None),
    municipality: Optional[str] = Form(None),
    barangay: Optional[str] = Form(None),
    address: Optional[str] = Form(None),
    latitude: Optional[float] = Form(0.0),
    longitude: Optional[float] = Form(0.0),
    contact_number: Optional[str] = Form(None),
    email: Optional[str] = Form(None),
    lto_number: Optional[str] = Form(None),
    lto_type: Optional[str] = Form(None),
    lto_issue_date: Optional[str] = Form(None),
    lto_expiration_date: Optional[str] = Form(None),
    lto_status: Optional[str] = Form("Active"),
    facility_status: str = Form("Active"),
    pso_daily_routing_limit: int = Form(5),
    lto_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db)
) -> AdminFacilityItem:
    """Provisions a new facility record with optional LTO license document attachment."""
    try:
        existing = db.query(Facility).filter(
            Facility.facility_name.ilike(facility_name.strip())
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Facility '{facility_name}' already exists (ID {existing.id})."
            )

        saved_file_path = None
        if lto_file and lto_file.filename:
            storage_dir = os.path.join("storage", "lto_files")
            os.makedirs(storage_dir, exist_ok=True)
            ext = os.path.splitext(lto_file.filename)[1]
            unique_filename = f"{uuid.uuid4().hex}{ext}"
            full_path = os.path.join(storage_dir, unique_filename)
            contents = await lto_file.read()
            with open(full_path, "wb") as f:
                f.write(contents)
            saved_file_path = f"/storage/lto_files/{unique_filename}"

        # Parse date fields if supplied
        parsed_issue_date = None
        if lto_issue_date:
            try:
                parsed_issue_date = datetime.strptime(lto_issue_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        parsed_exp_date = None
        if lto_expiration_date:
            try:
                parsed_exp_date = datetime.strptime(lto_expiration_date, "%Y-%m-%d").date()
            except ValueError:
                pass

        facility = Facility(
            facility_name=facility_name.strip(),
            facility_type=facility_type,
            ownership=ownership,
            facility_head=facility_head,
            region=region,
            province=province,
            municipality=municipality,
            barangay=barangay,
            address=address,
            latitude=latitude,
            longitude=longitude,
            contact_number=contact_number,
            email=email,
            lto_number=lto_number,
            lto_type=lto_type,
            lto_issue_date=parsed_issue_date,
            lto_expiration_date=parsed_exp_date,
            lto_status=lto_status,
            lto_file_path=saved_file_path,
            facility_status=facility_status,
            pso_daily_routing_limit=pso_daily_routing_limit,
            referrals_accepted_today=0,
        )

        db.add(facility)
        db.flush()
        facility.facility_code = f"FAC-{facility.id:06d}"

        # Provision default capability row
        cap = FacilityCapability(facility_id=facility.id)
        db.add(cap)

        db.commit()
        db.refresh(facility)

        item = AdminFacilityItem.model_validate(facility)
        item.has_api_key = False
        item.has_facility_user = False
        return item

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create facility: {str(e)}"
        )


@router.patch("/facilities/{facility_id}", response_model=AdminFacilityItem, summary="Update a facility")
async def update_facility(
    facility_id: int,
    payload: AdminFacilityUpdate,
    db: Session = Depends(get_db)
) -> AdminFacilityItem:
    """Applies a partial update to any facility's record."""
    try:
        facility = db.query(Facility).filter(Facility.id == facility_id).first()
        if not facility:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Facility record with ID {facility_id} not found."
            )

        update_data = payload.model_dump(exclude_unset=True)

        new_name = update_data.get("facility_name")
        if new_name and new_name.strip().lower() != (facility.facility_name or "").strip().lower():
            clash = db.query(Facility).filter(
                Facility.facility_name.ilike(new_name.strip()),
                Facility.id != facility_id
            ).first()
            if clash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Another facility already uses the name '{new_name}'."
                )

        for field, value in update_data.items():
            if value is not None:
                if field in ("lto_issue_date", "lto_expiration_date") and isinstance(value, str):
                    try:
                        value = datetime.strptime(value, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                setattr(facility, field, value.strip() if isinstance(value, str) else value)

        db.commit()
        db.refresh(facility)

        keyed = db.query(APIKey).filter(
            APIKey.hospital_name.ilike(facility.facility_name),
            APIKey.is_active == True
        ).first()
        fuser = db.query(FacilityUser).filter(FacilityUser.facility_id == facility.id).first()

        item = AdminFacilityItem.model_validate(facility)
        item.has_api_key = bool(keyed)
        item.has_facility_user = bool(fuser)
        item.facility_username = fuser.username if fuser else None
        return item

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update facility: {str(e)}"
        )


@router.delete("/facilities/{facility_id}", response_model=ActionResponse, summary="Remove a facility")
def delete_facility(facility_id: int, db: Session = Depends(get_db)) -> ActionResponse:
    """Deletes a facility record, refusing while it still has referral history on file."""
    try:
        facility = db.query(Facility).filter(Facility.id == facility_id).first()
        if not facility:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Facility record with ID {facility_id} not found."
            )

        name = facility.facility_name
        referral_count = db.query(func.count(Referral.referral_id)).filter(
            or_(Referral.referring_facility.ilike(name), Referral.receiving_facility.ilike(name))
        ).scalar() or 0

        if referral_count:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot delete '{name}': it is referenced by {referral_count} referral(s). "
                    "Deactivate its status instead."
                )
            )

        db.delete(facility)
        db.commit()
        return ActionResponse(message=f"Facility '{name}' was deleted.")

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete facility: {str(e)}"
        )


@router.post(
    "/facilities/{facility_id}/credentials",
    response_model=AdminFacilityCredentialsIssuedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue or reset facility admin credentials"
)
def issue_facility_credentials(
    facility_id: int,
    payload: Optional[AdminFacilityCredentialsCreate] = None,
    db: Session = Depends(get_db)
) -> AdminFacilityCredentialsIssuedResponse:
    """
    Issues or resets login credentials for a facility admin user.
    The plain password is returned ONLY in this response and never stored plaintext.
    """
    try:
        facility = db.query(Facility).filter(Facility.id == facility_id).first()
        if not facility:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Facility with ID {facility_id} not found."
            )

        existing_user = db.query(FacilityUser).filter(FacilityUser.facility_id == facility_id).first()

        # Determine username: custom payload > existing username > clean default name
        if payload and payload.username and payload.username.strip():
            desired_username = payload.username.strip()
        elif existing_user and existing_user.username:
            desired_username = existing_user.username
        else:
            clean_name = "".join(c.lower() for c in facility.facility_name if c.isalnum())[:10]
            desired_username = f"{clean_name}_admin"

        desired_role = (payload and payload.role) or "FACILITY_ADMIN"

        # Generate password if not provided
        raw_password = (payload and payload.password and payload.password.strip()) or secrets.token_hex(6)
        hashed_password = get_password_hash(raw_password)

        if existing_user:
            existing_user.username = desired_username
            existing_user.password_hash = hashed_password
            existing_user.role = desired_role
            existing_user.status = "Active"
            db.commit()
            return AdminFacilityCredentialsIssuedResponse(
                status="success",
                message=f"Credentials for '{facility.facility_name}' reset successfully.",
                facility_id=facility.id,
                facility_name=facility.facility_name,
                username=desired_username,
                raw_password=raw_password,
                role=desired_role
            )


        # Check username collision across facilities
        username_clash = db.query(FacilityUser).filter(FacilityUser.username == desired_username).first()
        if username_clash:
            desired_username = f"{desired_username}_{facility.id}"

        new_user = FacilityUser(
            facility_id=facility.id,
            username=desired_username,
            password_hash=hashed_password,
            role=desired_role,
            status="Active"
        )
        db.add(new_user)
        db.commit()

        return AdminFacilityCredentialsIssuedResponse(
            status="success",
            message=f"Credentials issued for '{facility.facility_name}'.",
            facility_id=facility.id,
            facility_name=facility.facility_name,
            username=desired_username,
            raw_password=raw_password,
            role=desired_role
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to issue credentials: {str(e)}"
        )


@router.get(
    "/credentials",
    response_model=list[AdminFacilityCredentialsItem],
    summary="List all facility credential statuses"
)
def list_facility_credentials(
    db: Session = Depends(get_db),
    search: Optional[str] = None,
) -> list[AdminFacilityCredentialsItem]:
    """Lists every registered facility alongside its login credential status."""
    query = db.query(Facility)
    if search and isinstance(search, str):
        query = query.filter(
            or_(
                Facility.facility_name.ilike(f"%{search.strip()}%"),
                Facility.facility_code.ilike(f"%{search.strip()}%")
            )
        )

    facilities = query.order_by(Facility.facility_name.asc()).all()

    facility_users = {
        fu.facility_id: fu
        for fu in db.query(FacilityUser).all()
    }

    items = []
    for f in facilities:
        fu = facility_users.get(f.id)
        items.append(
            AdminFacilityCredentialsItem(
                facility_id=f.id,
                facility_code=f.facility_code or f"FAC-{f.id:06d}",
                facility_name=f.facility_name,
                facility_type=f.facility_type,
                has_credentials=bool(fu and fu.status == "Active"),
                username=fu.username if fu else None,
                role=fu.role if fu else None,
                status=fu.status if fu else "Not Issued",
                created_at=fu.created_at if fu else None,
                last_login=fu.last_login if fu else None,
            )
        )
    return items



# BACKWARD COMPATIBILITY /hospitals ALIAS ENDPOINTS


@router.get("/hospitals", response_model=list[AdminFacilityItem], summary="List all hospitals (Alias for /facilities)")
def list_all_hospitals_alias(db: Session = Depends(get_db), search: Optional[str] = Query(None)):
    return list_all_facilities(db=db, search=search)


@router.post("/hospitals", response_model=AdminFacilityItem, status_code=status.HTTP_201_CREATED, summary="Create hospital (Alias)")
async def create_hospital_alias(payload: AdminHospitalCreate, db: Session = Depends(get_db)):
    return await create_facility(
        facility_name=payload.facility_name,
        facility_type=payload.facility_type,
        ownership=payload.ownership,
        facility_head=payload.facility_head,
        region=payload.region,
        province=payload.province,
        municipality=payload.municipality,
        barangay=payload.barangay,
        address=payload.address,
        latitude=payload.latitude,
        longitude=payload.longitude,
        contact_number=payload.contact_number,
        email=payload.email,
        lto_number=payload.lto_number,
        lto_type=payload.lto_type,
        lto_issue_date=payload.lto_issue_date,
        lto_expiration_date=payload.lto_expiration_date,
        lto_status=payload.lto_status,
        facility_status=payload.facility_status,
        pso_daily_routing_limit=payload.pso_daily_routing_limit,
        lto_file=None,
        db=db
    )


@router.patch("/hospitals/{hospital_id}", response_model=AdminFacilityItem, summary="Update hospital (Alias)")
async def update_hospital_alias(hospital_id: int, payload: AdminFacilityUpdate, db: Session = Depends(get_db)):
    return await update_facility(facility_id=hospital_id, payload=payload, db=db)


@router.delete("/hospitals/{hospital_id}", response_model=ActionResponse, summary="Delete hospital (Alias)")
def delete_hospital_alias(hospital_id: int, db: Session = Depends(get_db)):
    return delete_facility(facility_id=hospital_id, db=db)


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

        hospital = db.query(Facility).filter(
            Facility.facility_name.ilike(hospital_name)
        ).first()
        if not hospital:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No facility named '{hospital_name}' is registered. Add it under Facilities first."
            )

        existing = db.query(APIKey).filter(
            APIKey.hospital_name.ilike(hospital.facility_name),
            APIKey.is_active == True
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"'{hospital.facility_name}' already holds an active key (ID {existing.id}). "
                    "Rotate that key instead of minting a duplicate."
                )
            )

        raw_key, hashed_key, masked_display = generate_irdss_api_key(hospital.facility_name)
        api_key_rec = APIKey(
            hospital_name=hospital.facility_name,
            api_key=hashed_key,
            api_key_display=masked_display,
            is_active=True,
        )
        db.add(api_key_rec)
        db.commit()
        db.refresh(api_key_rec)

        return AdminApiKeyIssuedResponse(
            message=f"API Key successfully minted for '{hospital.facility_name}'. Copy it now; it will not be shown again.",
            raw_key=raw_key,
            key=_serialize_api_key(api_key_rec),
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to mint API key: {str(e)}"
        )


@router.patch("/api-keys/{key_id}", response_model=AdminApiKeyItem, summary="Toggle or reassign an API key")
def update_api_key(
    key_id: int,
    payload: AdminApiKeyUpdate,
    db: Session = Depends(get_db)
) -> AdminApiKeyItem:
    """Toggles active/revoked status or updates the owning hospital name on an existing key."""
    try:
        record = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key record with ID {key_id} not found."
            )

        if payload.hospital_name:
            new_name = payload.hospital_name.strip()
            hospital = db.query(Facility).filter(
                Facility.facility_name.ilike(new_name)
            ).first()
            if not hospital:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"No facility named '{new_name}' exists."
                )
            record.hospital_name = hospital.facility_name

        if payload.is_active is not None:
            record.is_active = bool(payload.is_active)

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


@router.post("/api-keys/{key_id}/rotate", response_model=AdminApiKeyIssuedResponse, summary="Rotate an API key")
def rotate_api_key(key_id: int, db: Session = Depends(get_db)) -> AdminApiKeyIssuedResponse:
    """Revokes the target key and mints a brand-new secret key for the same hospital in one operation."""
    try:
        old_record = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not old_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key record with ID {key_id} not found."
            )

        old_record.is_active = False

        raw_key, hashed_key, masked_display = generate_irdss_api_key(old_record.hospital_name)
        new_record = APIKey(
            hospital_name=old_record.hospital_name,
            api_key=hashed_key,
            api_key_display=masked_display,
            is_active=True,
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)

        return AdminApiKeyIssuedResponse(
            message=f"API key for '{old_record.hospital_name}' was rotated. Copy the new key now.",
            raw_key=raw_key,
            key=_serialize_api_key(new_record),
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


@router.delete("/api-keys/{key_id}", response_model=ActionResponse, summary="Revoke an API key")
def delete_api_key(key_id: int, db: Session = Depends(get_db)) -> ActionResponse:
    """Deletes an API key record permanently."""
    try:
        record = db.query(APIKey).filter(APIKey.id == key_id).first()
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key record with ID {key_id} not found."
            )

        hname = record.hospital_name
        db.delete(record)
        db.commit()
        return ActionResponse(message=f"API key for '{hname}' was revoked.")

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


@router.get("/system/health", response_model=SystemHealthResponse, summary="Gateway process and DB health check")
def get_system_health(
    window_minutes: int = Query(60, ge=1, le=1440),
    db: Session = Depends(get_db),
) -> SystemHealthResponse:
    """Probes DB latency and summarizes traffic metrics over the requested window."""
    db_connected = True
    db_error = None
    db_latency_ms = None

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
                "facilities": db.query(func.count(Facility.id)).scalar() or 0,
                "facility_users": db.query(func.count(FacilityUser.id)).scalar() or 0,
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
