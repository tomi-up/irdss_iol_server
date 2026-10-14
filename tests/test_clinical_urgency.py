import unittest
from types import SimpleNamespace
from pydantic import ValidationError
from fastapi import HTTPException
from app.schemas.encounter import ClinicalUrgencyRequest
from app.services.clinical_urgency import resolve_urgency
from app.services.emergency_routing import order_emergency_candidates

SYSTEM = 'https://irdss.gov.ph/fhir/CodeSystem/triage-acuity'

def payload(level='3', **extra):
    return ClinicalUrgencyRequest(triage={'system': SYSTEM, 'code': level},
        clinical_actor={'user_id': 'test-doctor', 'role': 'DOCTOR'}, **extra)

class ClinicalUrgencyTests(unittest.TestCase):
    def test_versioned_mapping_and_legacy_compatibility(self):
        for level, expected in enumerate(['routine', 'routine', 'urgent', 'asap', 'stat'], 1):
            self.assertEqual(resolve_urgency(payload(str(level)))['referral_priority'], expected)
            self.assertEqual(resolve_urgency(ClinicalUrgencyRequest(), level)['triage_code'], str(level))

    def test_condition_severity_does_not_change_triage_or_priority(self):
        result = resolve_urgency(payload('1', condition_severity={'system': 'http://snomed.info/sct', 'code': '24484000'}))
        self.assertEqual(result['triage_code'], '1')
        self.assertEqual(result['referral_priority'], 'routine')
        self.assertEqual(result['condition_severity_display'], 'Severe')

    def test_override_requires_a_reason(self):
        with self.assertRaises(HTTPException): resolve_urgency(payload('3', referral_priority='stat'))
        result = resolve_urgency(payload('3', referral_priority='stat', priority_override_reason='Clinician reassessment'))
        self.assertEqual(result['referral_priority'], 'stat')

    def test_invalid_values_and_non_doctor_are_rejected(self):
        for data in [payload('6'), payload('3', condition_severity={'system': 'http://snomed.info/sct', 'code': '233604007'})]:
            with self.assertRaises(HTTPException): resolve_urgency(data)
        with self.assertRaises(HTTPException): resolve_urgency(payload('3'), 2)
        data = payload(); data.clinical_actor.role = 'NURSE'
        with self.assertRaises(HTTPException) as caught: resolve_urgency(data)
        self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(ValidationError): payload('3', referral_priority='emergency')

    def test_deterministic_emergency_order_and_unknown_distance(self):
        patient = SimpleNamespace(latitude=7, longitude=125)
        hospitals = [SimpleNamespace(id=i, latitude=7+i/10, longitude=125) for i in [3, 2, 1]]
        hospitals.append(SimpleNamespace(id=4, latitude=None, longitude=None))
        capabilities = {i: SimpleNamespace(has_icu=i != 1, functional_beds=5) for i in [1, 2, 3, 4]}
        ordered = order_emergency_candidates(patient, hospitals, capabilities)
        self.assertEqual([h.id for h in ordered], [2, 3, 1])
