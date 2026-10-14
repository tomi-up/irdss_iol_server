"""Optional symptom coding never replaces the patient-specific narrative."""
from fastapi import HTTPException
from app.services.terminology_service import terminology_service, TerminologyServiceError


async def resolve_chief_complaint(concept, legacy_text=None):
    text = (concept.text if concept is not None else legacy_text) or ''
    text = text.strip() or None
    result = {"chief_complaint": text, "chief_complaint_text": text,
              "chief_complaint_system": None, "chief_complaint_code": None,
              "chief_complaint_display": None}
    if concept is None or not concept.coding:
        return result
    coding = concept.coding[0]
    try:
        validated = await terminology_service.validate_code('chief-complaint', system=coding.system, code=coding.code)
    except TerminologyServiceError as exc:
        raise HTTPException(503, 'Symptom validation is unavailable. Retry or keep text only.') from exc
    if not validated['valid']:
        raise HTTPException(422, 'Choose a symptom from the allowed results or keep text only.')
    result.update(chief_complaint_system=coding.system, chief_complaint_code=coding.code,
                  chief_complaint_display=validated['display'])
    return result


def complaint_fields(referral):
    return {key: getattr(referral, key, None) for key in (
        'chief_complaint_text', 'chief_complaint_system', 'chief_complaint_code', 'chief_complaint_display')}
