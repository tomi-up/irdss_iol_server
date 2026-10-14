import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from pydantic import ValidationError
from app.schemas.encounter import DiagnosisConcept
from app.services.clinical_diagnosis import resolve_diagnosis
from app.utils.diagnosis_capability import derive_required_capabilities


class ClinicalDiagnosisTests(unittest.IsolatedAsyncioTestCase):
    async def test_coded_diagnosis_uses_validated_display_and_keeps_text(self):
        concept = DiagnosisConcept.model_validate({"coding": [{"system": "http://snomed.info/sct",
            "code": "233604007", "display": "Wrong label"}], "text": "Possible pneumonia, right lung"})
        with patch('app.services.clinical_diagnosis.terminology_service.validate_code',
                   new=AsyncMock(return_value={"valid": True, "display": "Pneumonia"})):
            result = await resolve_diagnosis(concept)
        self.assertEqual(result["diagnosis_display"], "Pneumonia")
        self.assertEqual(result["diagnosis_text"], "Possible pneumonia, right lung")
        self.assertEqual(result["diagnosis_code"], "233604007")

    async def test_invalid_code_is_rejected(self):
        concept = DiagnosisConcept.model_validate({"coding": [{"system": "http://snomed.info/sct", "code": "25064002"}]})
        with patch('app.services.clinical_diagnosis.terminology_service.validate_code',
                   new=AsyncMock(return_value={"valid": False})):
            with self.assertRaises(HTTPException) as caught:
                await resolve_diagnosis(concept)
        self.assertEqual(caught.exception.status_code, 422)

    async def test_plain_text_legacy_and_empty_need_no_terminology(self):
        with patch('app.services.clinical_diagnosis.terminology_service.validate_code', new=AsyncMock()) as validate:
            result = await resolve_diagnosis(DiagnosisConcept(text="Undifferentiated illness"))
            self.assertEqual(result["diagnosis"], "Undifferentiated illness")
            self.assertIsNone(result["diagnosis_code"])
            self.assertEqual((await resolve_diagnosis(None, "Legacy impression"))["diagnosis_text"], "Legacy impression")
            self.assertIsNone((await resolve_diagnosis(None))["diagnosis"])
            validate.assert_not_called()

    def test_partial_coding_and_oversize_text_rejected(self):
        for data in ({"coding": [{"code": "233604007"}]}, {"text": "x" * 2001}):
            with self.assertRaises(ValidationError):
                DiagnosisConcept.model_validate(data)

    def test_code_based_matching_with_text_fallback(self):
        self.assertIn("has_neurologist", derive_required_capabilities("Atypical presentation",
            diagnosis_system="http://snomed.info/sct", diagnosis_code="230690007"))
        self.assertIn("has_cardiologist", derive_required_capabilities("chest pain"))
