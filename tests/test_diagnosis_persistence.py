"""Synthetic DB integration checks; only this test's records are removed."""
import unittest
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from app.database.db_connection import engine
from app.services.direct_patient_transfer import directory
from tests.test_direct_patient_transfer import php, request


class DiagnosisPersistenceTests(unittest.TestCase):
    def test_text_only_and_absent_diagnosis_are_not_referral_reason(self):
        source = next(item for item in directory().values() if item['name'] == 'DiWA Center')
        for diagnosis_text in (None, 'Working impression with no suitable coded diagnosis'):
            with self.subTest(diagnosis=diagnosis_text):
                person = {'id': 0, 'facility_id': source['local_facility_id'], 'first_name': 'Synthetic',
                    'last_name': uuid.uuid4().hex[:12], 'dob': '1990-01-01', 'gender': 'Male'}
                extensions = [{'url': 'http://irdss.gov.ph/fhir/StructureDefinition/' + key,
                    'valueString': value} for key, value in {
                        'consentStatus': 'GRANTED', 'consentMethod': 'PAPER',
                        'consentTextVersion': 'referral-consent-2026-09-v1',
                        'consentRecordedAt': datetime.now(timezone.utc).isoformat(),
                        'consentWitnessedBy': 'Synthetic clinician'}.items()]
                extensions.append({'url': 'http://irdss.gov.ph/fhir/StructureDefinition/severity', 'valueDecimal': 1})
                payload = {'resourceType': 'Encounter', 'status': 'planned',
                    'subject': {'reference': 'Patient/test'},
                    'reasonCode': [{'text': 'Service unavailable', 'coding': [{
                        'system': 'urn:irdss:reason', 'code': 'SERVICE', 'display': 'Not a diagnosis'}]}],
                    'patient_record': {'id': 'test', 'resourceType': 'Patient', 'gender': 'male',
                        'name': [], 'birthDate': person['dob'], 'extension': extensions}}
                if diagnosis_text is not None:
                    payload['diagnosis_concept'] = {'text': diagnosis_text, 'coding': []}
                prepared = php({'action': 'prepare', 'patient': person, 'payload': payload, 'full_name': 'Synthetic Patient'})
                referral_id = patient_id = None
                try:
                    code, created = request('POST', '/api/v1/referral/initiate', source, prepared['payload'])
                    self.assertEqual(code, 200, created)
                    referral_id = created['referral_id']
                    with engine.begin() as connection:
                        row = connection.execute(text('SELECT patient_id, diagnosis, diagnosis_text, '
                            'diagnosis_system, diagnosis_code, diagnosis_display FROM referrals '
                            'WHERE referral_id = :rid'), {'rid': referral_id}).mappings().one()
                        patient_id = row['patient_id']
                        self.assertEqual(row['diagnosis'], diagnosis_text)
                        self.assertEqual(row['diagnosis_text'], diagnosis_text)
                        for key in ('diagnosis_system', 'diagnosis_code', 'diagnosis_display'):
                            self.assertIsNone(row[key])
                finally:
                    php({'action': 'cleanup', 'transfer_id': prepared['transfer_id']})
                    if referral_id:
                        with engine.begin() as connection:
                            for table in ('referral_responses', 'referral_reasons', 'referrals'):
                                connection.execute(text(f'DELETE FROM {table} WHERE referral_id = :rid'), {'rid': referral_id})
                            if patient_id:
                                connection.execute(text('DELETE FROM patient_record WHERE fhir_id = :pid'), {'pid': patient_id})
