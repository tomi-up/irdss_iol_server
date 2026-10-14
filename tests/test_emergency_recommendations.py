import unittest
from types import SimpleNamespace
from unittest.mock import patch
from app.routers.referral import get_baseline_recommendations
from app.models.referral_model import Referral
from app.models.referral_response_model import ReferralResponse
from app.models.hospitals import Facility
from app.models.facility_capability import FacilityCapability

class Query:
    def __init__(self, rows): self.rows = rows
    def filter(self, *args): return self
    def first(self): return self.rows[0] if self.rows else None
    def all(self): return self.rows

class EmergencyRecommendationTests(unittest.TestCase):
    def fixture(self, level):
        patient = SimpleNamespace(latitude=7, longitude=125)
        referral = SimpleNamespace(referring_facility='Sender', triage_code=str(level), disease_severity=str(level),
            patient=patient, required_capability='has_cardiologist')
        hospitals = [SimpleNamespace(id=i, facility_name=f'Hospital {i}', facility_type='Level 3',
            latitude=7+i/10, longitude=125) for i in [1, 2, 3]]
        caps = [SimpleNamespace(facility_id=i, functional_beds=5, has_icu=i == 2) for i in [1, 2, 3]]
        rows = {Referral: [referral], ReferralResponse: [SimpleNamespace(hospital_name=h.facility_name) for h in hospitals],
            Facility: hospitals, FacilityCapability: caps}
        return SimpleNamespace(query=lambda model: Query(rows[model])), hospitals

    def test_emergency_bypasses_ai_and_excludes_ineligible_candidate(self):
        db, hospitals = self.fixture(5)
        with (patch('app.routers.referral.get_qualified_broadcast_targets', return_value=hospitals[:2]) as eligibility,
             patch('app.routers.referral.compute_compatibility_scores', side_effect=AssertionError('AI must not run'))):
            result = get_baseline_recommendations('synthetic', db, 'Sender')
        self.assertEqual([r['hospital_name'] for r in result], ['Hospital 2', 'Hospital 1'])
        self.assertTrue(all(r['ranking_method'] == 'DETERMINISTIC_EMERGENCY' for r in result))
        eligibility.assert_called_once_with(db, 5, ['has_cardiologist'])

    def test_non_emergency_still_uses_ai(self):
        db, _ = self.fixture(3)
        with patch('app.routers.referral.compute_compatibility_scores', return_value={'Hospital 3': .9, 'Hospital 1': .1}) as ai:
            result = get_baseline_recommendations('synthetic', db, 'Sender')
        ai.assert_called_once()
        self.assertEqual(result[0]['hospital_name'], 'Hospital 3')
