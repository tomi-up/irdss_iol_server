import unittest
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from pydantic import ValidationError
from app.schemas.encounter import ChiefComplaintConcept
from app.services.clinical_complaint import resolve_chief_complaint


class ClinicalComplaintTests(unittest.IsolatedAsyncioTestCase):
    async def test_symptom_never_replaces_narrative(self):
        concept = ChiefComplaintConcept(text='Severe chest pain radiating to the left arm',
            coding=[{'system': 'http://snomed.info/sct', 'code': '29857009', 'display': 'Wrong'}])
        with patch('app.services.clinical_complaint.terminology_service.validate_code',
                   new=AsyncMock(return_value={'valid': True, 'display': 'Chest pain'})):
            result = await resolve_chief_complaint(concept)
        self.assertEqual(result['chief_complaint'], concept.text)
        self.assertEqual(result['chief_complaint_text'], concept.text)
        self.assertEqual(result['chief_complaint_display'], 'Chest pain')
        self.assertEqual(result['chief_complaint_code'], '29857009')

    async def test_invalid_code_rejected(self):
        concept = ChiefComplaintConcept(text='Working complaint', coding=[{
            'system': 'http://snomed.info/sct', 'code': '233604007'}])
        with patch('app.services.clinical_complaint.terminology_service.validate_code',
                   new=AsyncMock(return_value={'valid': False})):
            with self.assertRaises(HTTPException) as caught:
                await resolve_chief_complaint(concept)
        self.assertEqual(caught.exception.status_code, 422)

    async def test_text_only_and_legacy_do_not_need_search(self):
        with patch('app.services.clinical_complaint.terminology_service.validate_code', new=AsyncMock()) as validate:
            result = await resolve_chief_complaint(ChiefComplaintConcept(text='Complex presentation'))
            self.assertIsNone(result['chief_complaint_code'])
            self.assertEqual(result['chief_complaint_text'], 'Complex presentation')
            self.assertEqual((await resolve_chief_complaint(None, 'Legacy narrative'))['chief_complaint_text'], 'Legacy narrative')
            validate.assert_not_called()

    def test_narrative_required_even_when_coded(self):
        for text in ('', '  ', 'x' * 2001):
            with self.assertRaises(ValidationError):
                ChiefComplaintConcept(text=text, coding=[{'system': 'http://snomed.info/sct', 'code': '29857009'}])
