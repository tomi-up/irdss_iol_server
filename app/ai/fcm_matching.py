import math

from app.models.hospitals import Facility
from app.models.patient_model import PatientRecords

# Weights for each dimension of the patient/facility distance vector.
# Clinical safety (severity match) dominates; budget/geo/capacity are secondary.
WEIGHT_SEVERITY = 1.5
WEIGHT_DISTANCE = 1.0
WEIGHT_BUDGET = 1.0
WEIGHT_LOAD = 0.75
WEIGHT_BEDS = 0.75

# Normalization caps
MAX_RELEVANT_DISTANCE_KM = 100.0
MAX_RELEVANT_BEDS = 20.0

# Fixed budget tiers for PatientRecords.salary (expected out-of-pocket limit)
BUDGET_TIER_LOW_MAX = 10000.0
BUDGET_TIER_MID_MAX = 25000.0

# FCM fuzziness exponent (standard choice is m=2, giving exponent 2/(m-1) = 2)
FUZZINESS_EXPONENT = 2

_LEVEL_TIER = {
    "Level 1": 1, "Level 1 Hospital": 1,
    "Level 2": 2, "Level 2 Hospital": 2,
    "Level 3": 3, "Level 3 Hospital": 3,
    "RHU": 1, "BHS": 1
}


def _facility_level_tier(facility_type: str) -> int:
    return _LEVEL_TIER.get(facility_type, 2)


def _required_severity_tier(patient_severity: int) -> int:
    if patient_severity >= 3:
        return 3
    if patient_severity == 2:
        return 2
    return 1


def _budget_tier(salary: float) -> int:
    if salary <= BUDGET_TIER_LOW_MAX:
        return 1
    if salary <= BUDGET_TIER_MID_MAX:
        return 2
    return 3


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    if None in (lat1, lon1, lat2, lon2):
        return MAX_RELEVANT_DISTANCE_KM

    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def _facility_distance(patient: PatientRecords, facility: Facility) -> float:
    """
    Weighted Euclidean distance between a patient's needs and a single facility's
    real-time capability profile, across severity, geography, budget, and current load.
    Every term is normalized to [0, 1] before weighting.
    """
    required_tier = _required_severity_tier(patient.severity or 0)
    facility_tier = _facility_level_tier(facility.facility_type)
    severity_gap = max(0, required_tier - facility_tier) / 2.0

    distance_km = _haversine_km(patient.latitude, patient.longitude, facility.latitude, facility.longitude)
    geo_gap = min(distance_km / MAX_RELEVANT_DISTANCE_KM, 1.0)

    patient_budget_tier = _budget_tier(patient.salary or 0.0)
    budget_gap = abs(patient_budget_tier - facility_tier) / 2.0

    daily_limit = max(facility.pso_daily_routing_limit or 1, 1)
    load_gap = min((facility.referrals_accepted_today or 0) / daily_limit, 1.0)

    beds_count = getattr(facility, 'functional_beds', 0)
    if hasattr(facility, 'capability') and facility.capability:
        beds_count = facility.capability.functional_beds or 0
    bed_gap = 1.0 - min((beds_count or 0) / MAX_RELEVANT_BEDS, 1.0)

    return math.sqrt(
        (WEIGHT_SEVERITY * severity_gap) ** 2 +
        (WEIGHT_DISTANCE * geo_gap) ** 2 +
        (WEIGHT_BUDGET * budget_gap) ** 2 +
        (WEIGHT_LOAD * load_gap) ** 2 +
        (WEIGHT_BEDS * bed_gap) ** 2
    )


def compute_compatibility_scores(
    patient: PatientRecords,
    facilities: list[Facility]
) -> dict[str, float]:
    """
    Computes a Fuzzy C-Means style membership degree (u_j) for the given patient
    against each candidate facility. Returns {facility_name: u_j}, where values sum to 1.0.
    """
    if not facilities:
        return {}

    if len(facilities) == 1:
        return {facilities[0].facility_name: 1.0}

    distances = {f.facility_name: _facility_distance(patient, f) for f in facilities}

    zero_distance_facilities = [name for name, d in distances.items() if d == 0]
    if zero_distance_facilities:
        winner = zero_distance_facilities[0]
        return {name: (1.0 if name == winner else 0.0) for name in distances}

    scores = {}
    for name, d_j in distances.items():
        denom = sum((d_j / d_k) ** FUZZINESS_EXPONENT for d_k in distances.values())
        scores[name] = 1.0 / denom if denom else 0.0

    return scores
