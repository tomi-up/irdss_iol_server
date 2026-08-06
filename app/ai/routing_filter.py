from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.hospitals import HospitalResources

def get_qualified_broadcast_targets(db: Session, patient_severity: int) -> list[HospitalResources]:
    """
    Executes a fast, rule-based clinical check to identify qualified candidate
    hospitals that have available beds, match the patient's triage severity, and
    have not yet exhausted their PSO-computed daily routing capacity [cite: 95, 99, 110].
    """
    # 1. Establish the base query
    query = db.query(HospitalResources).filter(
        HospitalResources.available_beds > 0,  # Hospital must have bed space
        # PSO daily capacity gate: skip hospitals that already hit today's accepted-referral cap [cite: 110]
        func.coalesce(HospitalResources.referrals_accepted_today, 0)
        < func.coalesce(HospitalResources.pso_daily_routing_limit, 5)
    )

    # 2. Apply clinical triage constraints:
    # - Severity 3 (Severe/Critical): Requires Level 3 (Apex) and Emergency Equipment [cite: 259, 261].
    # - Severity 2 (Moderate/Urgent): Requires Level 2 or 3 and basic Medical Equipment [cite: 261, 275].
    # - Severity 1 (Mild/Non-urgent): Can be handled by Level 1, 2, or 3 [cite: 261, 275].
    if patient_severity >= 3:
        query = query.filter(
            HospitalResources.hospital_level == "Level 3",
            HospitalResources.emergency_equipment == True  # E.g., crash carts & intubation
        )
    elif patient_severity == 2:
        query = query.filter(
            HospitalResources.hospital_level.in_(["Level 2", "Level 3"]),
            HospitalResources.medical_equipment == True  # Requires diagnostics/intervention capacity
        )
    else:
        query = query.filter(
            HospitalResources.hospital_level.in_(["Level 1", "Level 2", "Level 3"]),
            HospitalResources.communication_systems == True  # Must be online
        )

    return query.all()