"""Phase 4 diagnosis adapter; Condition construction belongs to Phase 7."""
from fastapi import HTTPException
from app.services.terminology_service import terminology_service, TerminologyServiceError


async def resolve_diagnosis(concept, legacy_text=None):
    if concept is None:
        text = (legacy_text or "").strip() or None
        return {"diagnosis_system": None, "diagnosis_code": None,
                "diagnosis_display": None, "diagnosis_text": text, "diagnosis": text}
    text = (concept.text or "").strip() or None
    if not concept.coding:
        return {"diagnosis_system": None, "diagnosis_code": None,
                "diagnosis_display": None, "diagnosis_text": text, "diagnosis": text}
    coding = concept.coding[0]
    try:
        validated = await terminology_service.validate_code(
            "diagnosis", system=coding.system, code=coding.code)
    except TerminologyServiceError as exc:
        raise HTTPException(503, "Diagnosis validation is unavailable. Retry or use text only.") from exc
    if not validated["valid"]:
        raise HTTPException(422, "Choose a diagnosis from the allowed results or use free text.")
    return {"diagnosis_system": coding.system, "diagnosis_code": coding.code,
            "diagnosis_display": validated["display"], "diagnosis_text": text,
            "diagnosis": text or validated["display"]}


def diagnosis_fields(referral):
    return {key: getattr(referral, key, None) for key in (
        "diagnosis_system", "diagnosis_code", "diagnosis_display", "diagnosis_text")}
