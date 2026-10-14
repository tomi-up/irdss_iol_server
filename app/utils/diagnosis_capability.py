from typing import Optional

# Maps FacilityCapability boolean columns to keywords that, if found in the
# referral's diagnosis/chief complaint/clinical reason text, mean a candidate
# facility MUST have that capability to be a safe match. Keep keys aligned to
# actual column names on app.models.facility_capability.FacilityCapability.
_CAPABILITY_KEYWORDS: dict[str, list[str]] = {
    "has_hemodialysis": ["dialysis", "renal failure", "kidney failure", "ckd", "esrd"],
    "has_delivery_room": ["labor", "delivery", "obstetric", "pregnan", "childbirth"],
    "has_obgyn": ["labor", "delivery", "obstetric", "pregnan", "gynecolog"],
    "has_neurologist": ["stroke", "seizure", "neurolog", "cva"],
    "has_cardiologist": ["cardiac", "myocardial", "heart attack", "chest pain", "arrhythmia"],
    "has_general_surgeon": ["trauma", "fracture", "laceration", "appendicitis", "surgical", "gunshot", "stab wound"],
    "has_nicu": ["neonat", "premature infant", "newborn distress"],
    "has_blood_bank": ["hemorrhage", "transfusion", "severe bleeding"],
}


def derive_required_capabilities(*texts: Optional[str], diagnosis_system=None, diagnosis_code=None) -> list[str]:
    """
    Scans the given free-text clinical fields (diagnosis, chief complaint, reason)
    for keywords indicating the patient needs a specific facility capability beyond
    the baseline severity tier check (e.g. dialysis, OB delivery, neurology).
    Returns the list of FacilityCapability column names that must be True.
    """
    combined = " ".join(t for t in texts if t).lower()
    # Prototype code rules preserve existing capability categories; they are not
    # treatment recommendations or a replacement for clinician assessment.
    coded = {
        "398254007": ["has_obgyn"],
        "230690007": ["has_neurologist"],
        "57054005": ["has_cardiologist"],
        "74400008": ["has_general_surgeon"],
    }.get(diagnosis_code, []) if diagnosis_system == "http://snomed.info/sct" else []
    return sorted(set(coded + [
        capability
        for capability, keywords in _CAPABILITY_KEYWORDS.items()
        if any(keyword in combined for keyword in keywords)
    ]))
