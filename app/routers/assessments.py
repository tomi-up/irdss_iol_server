import logging
from typing import Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database.db_connection import get_db
from app.models.hospitals import Facility
from app.models.facility_capability import FacilityCapability
from app.models.assessment_models import FacilityAssessment, AssessmentAnswer
from app.utils.doh_forms import get_premade_doh_form
from app.utils.crypto_auth import verify_crypto_request_signature, SystemIdentityContext
from app.utils.three_layer_auth import enforce_three_layer_auth, ThreeLayerAuthContext, verify_object_facility_ownership

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/assessments", tags=["Pre-Made DOH Service Assessments"])


# Pydantic Schemas
class AssessmentAnswerItemSchema(BaseModel):
    category: str
    item_code: str
    item_label: str
    available: Optional[bool] = None
    operational: Optional[bool] = None
    adequate: Optional[bool] = None
    compliance: Optional[str] = None
    count: Optional[int] = None
    remarks: Optional[str] = None


class FacilityAssessmentSubmitPayload(BaseModel):
    facility_id: int
    assessment_type: str = "Monitoring"
    assessment_date: Optional[str] = None
    assessment_period: Optional[str] = None
    assessor_name: Optional[str] = None
    general_remarks: Optional[str] = None
    answers: List[AssessmentAnswerItemSchema]


class FacilityAssessmentSubmitResponse(BaseModel):
    status: str = "success"
    message: str
    assessment_id: int
    submitted_at: datetime


@router.get("/form", summary="Get built-in pre-made DOH Assessment form for facility")
def get_doh_assessment_form(
    facility_id: Optional[int] = None,
    facility_code: Optional[str] = None,
    facility_name: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Returns the built-in pre-made DOH Service Assessment form (Hospital, RHU, or BHS)
    based on the facility's type & level. Includes existing submitted answers if present.
    """
    facility = None
    if facility_id:
        facility = db.query(Facility).filter(Facility.id == facility_id).first()
    if not facility and facility_code:
        facility = db.query(Facility).filter(Facility.facility_code.ilike(facility_code)).first()
    # Local facility-side systems (e.g. mock_hospitals) may provision their own facility
    # codes that don't match the central registry's — fall back to matching by name,
    # same pattern get_current_hospital() in referral.py already relies on.
    if not facility and facility_name:
        facility = db.query(Facility).filter(Facility.facility_name.ilike(facility_name)).first()

    fac_type = (facility and facility.facility_type and facility.facility_type.upper()) or "HOSPITAL"
    fac_level = (facility and facility.facility_type and "LEVEL" in facility.facility_type.upper() and facility.facility_type.upper()) or "LEVEL_1"

    if "RHU" in fac_type or "RURAL" in fac_type:
        fac_type = "RHU"
        fac_level = "PRIMARY_CARE"
    elif "BHS" in fac_type or "BARANGAY" in fac_type:
        fac_type = "BHS"
        fac_level = "PRIMARY_CARE"
    elif "LEVEL 2" in fac_type or "LEVEL_2" in fac_type:
        fac_type = "HOSPITAL"
        fac_level = "LEVEL_2"
    elif "LEVEL 3" in fac_type or "LEVEL_3" in fac_type:
        fac_type = "HOSPITAL"
        fac_level = "LEVEL_3"
    else:
        fac_type = "HOSPITAL"
        fac_level = "LEVEL_1"

    # Load built-in pre-made form structure
    form_structure = get_premade_doh_form(fac_type, fac_level)

    # Fetch previous submission if available
    previous_answers = {}
    last_assessment = None
    if facility:
        last_assessment = db.query(FacilityAssessment).filter(
            FacilityAssessment.facility_id == facility.id
        ).order_by(FacilityAssessment.submitted_at.desc()).first()

        if last_assessment:
            answers_rows = db.query(AssessmentAnswer).filter(
                AssessmentAnswer.facility_assessment_id == last_assessment.id
            ).all()

            for ans in answers_rows:
                previous_answers[ans.item_code] = {
                    "category": ans.category,
                    "item_code": ans.item_code,
                    "available": ans.available,
                    "operational": ans.operational,
                    "adequate": ans.adequate,
                    "compliance": ans.compliance,
                    "count": ans.count,
                    "remarks": ans.remarks
                }

    return {
        "facility_id": facility.id if facility else None,
        "facility_code": facility.facility_code if facility else facility_code,
        "facility_name": facility.facility_name if facility else "Unknown Facility",
        "facility_type": fac_type,
        "facility_level": fac_level,
        "form": form_structure,
        "previous_submission": {
            "assessment_id": last_assessment.id if last_assessment else None,
            "assessment_type": last_assessment.assessment_type if last_assessment else None,
            "assessment_date": last_assessment.assessment_date if last_assessment else None,
            "assessment_period": last_assessment.assessment_period if last_assessment else None,
            "assessor_name": last_assessment.assessor_name if last_assessment else None,
            "general_remarks": last_assessment.general_remarks if last_assessment else None,
            "submitted_at": last_assessment.submitted_at if last_assessment else None,
            "answers": previous_answers
        } if last_assessment else None
    }


@router.post("/submit", response_model=FacilityAssessmentSubmitResponse, summary="Submit completed DOH service assessment to PostgreSQL")
def submit_doh_assessment(
    payload: FacilityAssessmentSubmitPayload,
    db: Session = Depends(get_db),
    auth_ctx: ThreeLayerAuthContext = Depends(enforce_three_layer_auth)
):
    """
    Saves a completed pre-made DOH service assessment to PostgreSQL after 3-Layer Auth check.
    """
    verify_object_facility_ownership(auth_ctx, target_facility_id=payload.facility_id)

    facility = auth_ctx.facility

    try:
        # Create Header
        assessment = FacilityAssessment(
            facility_id=facility.id,
            facility_type=facility.facility_type or "HOSPITAL",
            facility_level=facility.facility_type or "LEVEL_1",
            assessment_type=payload.assessment_type or "Monitoring",
            assessment_date=payload.assessment_date,
            assessment_period=payload.assessment_period,
            assessor_name=payload.assessor_name,
            general_remarks=payload.general_remarks,
            status="SUBMITTED",
            submitted_at=datetime.now(timezone.utc)
        )
        db.add(assessment)
        db.flush()

        answers_to_insert = []
        capability_updates = {}

        for ans in payload.answers:
            answers_to_insert.append(
                AssessmentAnswer(
                    facility_assessment_id=assessment.id,
                    category=ans.category,
                    item_code=ans.item_code,
                    item_label=ans.item_label,
                    available=ans.available,
                    operational=ans.operational,
                    adequate=ans.adequate,
                    compliance=ans.compliance,
                    count=ans.count,
                    remarks=ans.remarks
                )
            )

            # Map boolean/number fields to FacilityCapability for referral engine
            if ans.item_code == "icu" or ans.item_code == "has_icu":
                capability_updates["has_icu"] = ans.available if ans.available is not None else False
            elif ans.item_code == "er" or ans.item_code == "has_er_trauma":
                capability_updates["has_er_trauma"] = ans.available if ans.available is not None else False
            elif ans.item_code == "ct_mri" or ans.item_code == "eq_xray":
                capability_updates["has_ct_mri"] = ans.available if ans.available is not None else False
            elif ans.item_code == "functional_beds" and ans.count is not None:
                capability_updates["functional_beds"] = ans.count
            elif ans.item_code == "dialysis":
                capability_updates["has_hemodialysis"] = ans.available if ans.available is not None else False
            elif ans.item_code == "nicu":
                capability_updates["has_nicu"] = ans.available if ans.available is not None else False
            elif ans.item_code == "obgyn_service":
                obgyn_available = ans.available if ans.available is not None else False
                capability_updates["has_obgyn"] = obgyn_available
                capability_updates["has_delivery_room"] = obgyn_available
            elif ans.item_code == "blood_bank":
                capability_updates["has_blood_bank"] = ans.available if ans.available is not None else False
            elif ans.item_code == "gensurg_service":
                capability_updates["has_general_surgeon"] = ans.available if ans.available is not None else False
            elif ans.item_code == "cardio_service":
                capability_updates["has_cardiologist"] = ans.available if ans.available is not None else False
            elif ans.item_code == "neuro_service":
                capability_updates["has_neurologist"] = ans.available if ans.available is not None else False

        db.add_all(answers_to_insert)

        # Sync capability metrics
        cap = db.query(FacilityCapability).filter(FacilityCapability.facility_id == facility.id).first()
        if not cap:
            cap = FacilityCapability(facility_id=facility.id)
            db.add(cap)

        for k, v in capability_updates.items():
            if hasattr(cap, k):
                setattr(cap, k, v)

        db.commit()

        return FacilityAssessmentSubmitResponse(
            status="success",
            message=f"DOH Service Assessment for '{facility.facility_name}' saved successfully.",
            assessment_id=assessment.id,
            submitted_at=assessment.submitted_at
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to submit DOH assessment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save assessment to database: {str(e)}"
        )
