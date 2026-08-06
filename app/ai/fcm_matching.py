import math

from app.models.hospitals import HospitalResources
from app.models.patient_model import PatientRecords

# Weights for each dimension of the patient/hospital distance vector.
# Clinical safety (severity match) dominates; budget/geo/capacity are secondary.
WEIGHT_SEVERITY = 1.5
WEIGHT_DISTANCE = 1.0
WEIGHT_BUDGET = 1.0
WEIGHT_LOAD = 0.75
WEIGHT_BEDS = 0.75

# Normalization caps
MAX_RELEVANT_DISTANCE_KM = 100.0
MAX_RELEVANT_BEDS = 20.0

# Fixed budget tiers for PatientRecords.salary (expected out-of-pocket limit),
# since HospitalResources has no cost field to compare against directly.
BUDGET_TIER_LOW_MAX = 10000.0
BUDGET_TIER_MID_MAX = 25000.0

# FCM fuzziness exponent (standard choice is m=2, giving exponent 2/(m-1) = 2)
FUZZINESS_EXPONENT = 2

_LEVEL_TIER = {"Level 1": 1, "Level 2": 2, "Level 3": 3}


def _hospital_level_tier(hospital_level: str) -> int:
    return _LEVEL_TIER.get(hospital_level, 2)


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


def _hospital_distance(patient: PatientRecords, hospital: HospitalResources) -> float:
    """
    Weighted Euclidean distance between a patient's needs and a single hospital's
    real-time capability profile, across severity, geography, budget, and current load.
    Every term is normalized to [0, 1] before weighting.
    """
    required_tier = _required_severity_tier(patient.severity or 0)
    hospital_tier = _hospital_level_tier(hospital.hospital_level)
    severity_gap = max(0, required_tier - hospital_tier) / 2.0

    distance_km = _haversine_km(patient.latitude, patient.longitude, hospital.latitude, hospital.longitude)
    geo_gap = min(distance_km / MAX_RELEVANT_DISTANCE_KM, 1.0)

    patient_budget_tier = _budget_tier(patient.salary or 0.0)
    budget_gap = abs(patient_budget_tier - hospital_tier) / 2.0

    daily_limit = max(hospital.pso_daily_routing_limit or 1, 1)
    load_gap = min((hospital.referrals_accepted_today or 0) / daily_limit, 1.0)

    bed_gap = 1.0 - min((hospital.available_beds or 0) / MAX_RELEVANT_BEDS, 1.0)

    return math.sqrt(
        (WEIGHT_SEVERITY * severity_gap) ** 2 +
        (WEIGHT_DISTANCE * geo_gap) ** 2 +
        (WEIGHT_BUDGET * budget_gap) ** 2 +
        (WEIGHT_LOAD * load_gap) ** 2 +
        (WEIGHT_BEDS * bed_gap) ** 2
    )


def compute_compatibility_scores(
    patient: PatientRecords,
    hospitals: list[HospitalResources]
) -> dict[str, float]:
    """
    Computes a Fuzzy C-Means style membership degree (u_j) for the given patient
    against each candidate hospital, treating every accepting hospital as a fixed
    cluster center in a normalized [severity, distance, budget, load, beds] feature
    space. Returns {hospital_name: u_j}, where values sum to 1.0 across the pool.
    """
    if not hospitals:
        return {}

    if len(hospitals) == 1:
        return {hospitals[0].hospital_name: 1.0}

    distances = {h.hospital_name: _hospital_distance(patient, h) for h in hospitals}

    zero_distance_hospitals = [name for name, d in distances.items() if d == 0]
    if zero_distance_hospitals:
        winner = zero_distance_hospitals[0]
        return {name: (1.0 if name == winner else 0.0) for name in distances}

    scores = {}
    for name, d_j in distances.items():
        denom = sum((d_j / d_k) ** FUZZINESS_EXPONENT for d_k in distances.values())
        scores[name] = 1.0 / denom if denom else 0.0

    return scores
