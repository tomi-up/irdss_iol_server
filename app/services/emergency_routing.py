"""Deterministic prototype ordering, never a substitute for transfer-safety review."""
import math

CAPABILITIES = ('has_icu', 'has_nicu', 'has_er_trauma', 'has_delivery_room', 'has_hemodialysis',
    'has_blood_bank', 'has_ct_mri', 'has_cardiologist', 'has_obgyn', 'has_neurologist', 'has_general_surgeon')

def distance_km(patient, facility):
    coordinates = [getattr(patient, 'latitude', None), getattr(patient, 'longitude', None),
                   getattr(facility, 'latitude', None), getattr(facility, 'longitude', None)]
    if any(v is None or not math.isfinite(float(v)) for v in coordinates):
        return math.inf
    a, b, c, d = map(lambda v: math.radians(float(v)), coordinates)
    h = math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 6371 * 2 * math.asin(math.sqrt(max(0, min(1, h))))

def order_emergency_candidates(patient, hospitals, capability_by_id):
    def key(facility):
        cap = capability_by_id.get(facility.id)
        score = sum(bool(getattr(cap, field, False)) for field in CAPABILITIES)
        return (-score, distance_km(patient, facility), -int(getattr(cap, 'functional_beds', 0) or 0), facility.id)
    return sorted([h for h in hospitals if math.isfinite(distance_km(patient, h))], key=key)
