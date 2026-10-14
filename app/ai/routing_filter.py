from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.hospitals import Facility
from app.models.facility_capability import FacilityCapability

def get_qualified_broadcast_targets(
    db: Session,
    patient_severity: int,
    required_capabilities: list[str] | None = None
) -> list[Facility]:
    """
    Executes a fast, rule-based clinical check to identify qualified candidate
    facilities that have available beds, match the patient's triage severity,
    have the specific clinical capabilities the diagnosis calls for (e.g. dialysis,
    OB delivery, neurology — see app.utils.diagnosis_capability), and have not yet
    exhausted their PSO-computed daily routing capacity.
    """
    # 1. Establish the base query joining Facility and FacilityCapability
    query = db.query(Facility).join(
        FacilityCapability, FacilityCapability.facility_id == Facility.id
    ).filter(
        Facility.facility_status == "Active",
        FacilityCapability.functional_beds > 0,  # Facility must have bed space
        # PSO daily capacity gate: skip facilities that already hit today's accepted-referral cap
        func.coalesce(Facility.referrals_accepted_today, 0)
        < func.coalesce(Facility.pso_daily_routing_limit, 5)
    )

    # 2. Apply clinical triage constraints:
    # - Severity >= 3 (Severe/Critical): Requires Level 3 Hospital and ER Trauma capability
    # - Severity == 2 (Moderate/Urgent): Requires Level 2 or Level 3 Hospital and ICU capability
    # - Severity == 1 (Mild/Non-urgent): Can be handled by any active Level 1-3 hospital or RHU/BHS
    if patient_severity >= 3:
        query = query.filter(
            Facility.facility_type.in_(["Level 3", "Level 3 Hospital"]),
            FacilityCapability.has_er_trauma == True
        )
    elif patient_severity == 2:
        query = query.filter(
            Facility.facility_type.in_(["Level 2", "Level 3", "Level 2 Hospital", "Level 3 Hospital"]),
            FacilityCapability.has_icu == True
        )
    else:
        query = query.filter(
            Facility.facility_type.in_(["Level 1", "Level 2", "Level 3", "Level 1 Hospital", "Level 2 Hospital", "Level 3 Hospital", "RHU", "BHS"])
        )

    # 3. Diagnosis-derived capability requirements (e.g. a dialysis patient can only
    # go to a facility with has_hemodialysis == True, regardless of severity tier)
    for capability in (required_capabilities or []):
        if hasattr(FacilityCapability, capability):
            query = query.filter(getattr(FacilityCapability, capability) == True)

    return query.all()