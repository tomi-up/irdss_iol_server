"""Cross-language and live HTTP checks with a synthetic referral; fixture is removed."""
import base64
import copy
import hashlib
import json
import os
import subprocess
import time
import unittest
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from pydantic import ValidationError
from sqlalchemy import text

from app.database.db_connection import engine
from app.schemas.encounter import ReferralRequestSchema
from app.services.direct_patient_transfer import directory, issue_ticket, verify_ticket
from app.utils.security import aes_decrypt

MOCK = Path('C:/laragon/www/mock_hospitals')
PHP = 'C:/laragon/bin/php/php-8.3.30-Win32-vs16-x64/php.exe'


def php(input_data, expect_error=False):
    process = subprocess.run([PHP, str(MOCK / 'tests/direct_patient_transfer_runner.php')],
        input=json.dumps(input_data), text=True, capture_output=True)
    result = json.loads(process.stdout)
    if process.returncode and not expect_error:
        raise AssertionError(result)
    return result


def request(method, path, facility, data=None):
    body = json.dumps(data).encode() if data is not None else b''
    timestamp = str(int(time.time()))
    nonce = uuid.uuid4().hex
    unsigned = '\n'.join([method, path, 'SYSTEM-001', 'KEY-2026-001', timestamp, nonce,
                          hashlib.sha256(body).hexdigest()])
    key = serialization.load_pem_private_key((MOCK / 'storage/keys/private_key.pem').read_bytes(), None)
    signature = key.sign(unsigned.encode(), padding.PKCS1v15(), hashes.SHA256())
    req = urllib.request.Request('http://127.0.0.1:8081' + path, data=body if data is not None else None,
        method=method, headers={'Content-Type': 'application/json', 'X-System-Code': 'SYSTEM-001',
        'X-Key-ID': 'KEY-2026-001', 'X-Signature-Timestamp': timestamp, 'X-Request-Nonce': nonce,
        'X-System-Signature': base64.b64encode(signature).decode(),
        'X-Facility-Code': facility['local_code'], 'X-Facility-Name': facility['name']})
    if os.getenv('IRDSS_TEST_IN_PROCESS') == '1':
        from fastapi.testclient import TestClient
        from app.main import app
        response = TestClient(app).request(method, path, content=body if data is not None else None,
                                          headers=dict(req.header_items()))
        return response.status_code, response.json()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


class DirectPatientTransferTests(unittest.TestCase):
    def test_full_exchange_and_privacy_boundary(self):
        entries = directory()
        source_code = next(code for code, item in entries.items() if item['name'] == 'DiWA Center')
        recipient_code = next(code for code in entries if code != source_code)
        source, recipient = entries[source_code], entries[recipient_code]
        person = {'id': 0, 'facility_id': source['local_facility_id'], 'first_name': 'Synthetic',
                  'middle_name': 'Transfer', 'last_name': uuid.uuid4().hex[:8], 'dob': '1990-01-01', 'gender': 'Male'}
        full_name = ' '.join([person['first_name'], person['middle_name'], person['last_name']])
        extensions = [
            {'url': 'http://irdss.gov.ph/fhir/StructureDefinition/' + name, 'valueString': value}
            for name, value in {'consentStatus': 'GRANTED', 'consentMethod': 'PAPER',
                'consentTextVersion': 'referral-consent-2026-09-v1',
                'consentRecordedAt': datetime.now(timezone.utc).isoformat(),
                'consentWitnessedBy': 'Synthetic clinician', 'phone': 'TEST-PHONE'}.items()
        ] + [{'url': 'http://irdss.gov.ph/fhir/StructureDefinition/severity', 'valueDecimal': 1}]
        payload = {'resourceType': 'Encounter', 'status': 'planned',
            'triage': {'system': 'https://irdss.gov.ph/fhir/CodeSystem/triage-acuity', 'code': '1'},
            'referral_priority': 'urgent', 'priority_override_reason': 'Synthetic doctor override',
            'clinical_actor': {'user_id': 'synthetic-doctor', 'role': 'DOCTOR'},
            'condition_severity': {'system': 'http://snomed.info/sct', 'code': '24484000'},
            'chief_complaint_concept': {'text': 'Severe chest pain radiating to the left arm', 'coding': [{
                'system': 'http://snomed.info/sct', 'code': '29857009', 'display': 'Wrong symptom label'}]},
            'diagnosis_concept': {'text': 'Possible pneumonia, right lung', 'coding': [{
                'system': 'http://snomed.info/sct', 'code': '233604007', 'display': 'Tampered label'}]},
            'subject': {'reference': 'Patient/test', 'display': full_name},
            'reasonCode': [{'text': 'Synthetic exchange test'}],
            'patient_record': {'id': 'test', 'resourceType': 'Patient', 'name': [{'given': ['Synthetic'],
                'family': person['last_name']}], 'birthDate': person['dob'], 'gender': 'male', 'extension': extensions}}
        payload['clinical_bundle']=php({'action':'build-clinical','payload':payload,
            'user':{'id':'synthetic-doctor','facility':{'name':source['name'],'code':source['local_code']}},
            'vitals':{'vital_bp':'120/80','vital_hr':'72','vital_rr':'18','vital_temp_c':'36.5','vital_o2sat':'98','vital_height_cm':'170','vital_weight_kg':'65'},
            'observed_at':datetime.now(timezone.utc).isoformat(),'oxygen_method':'pulse-oximetry'})
        payload['patient_record']['extension'].extend([
            {'url':'http://irdss.gov.ph/fhir/StructureDefinition/'+name,'valueString':'legacy copy'}
            for name in ('diagnosis','chiefComplaint','vitalBloodPressure')])
        prepared = php({'action': 'prepare', 'patient': person, 'payload': payload, 'full_name': full_name})
        transfer_id = prepared['transfer_id']
        referral_id = None
        patient_id = None
        vault_root = Path(__file__).resolve().parents[1] / 'storage/patient_identity_vault'
        try:
            route = prepared['payload']
            self.assertFalse(any(e['url'].rsplit('/',1)[-1] in ('diagnosis','chiefComplaint','vitalBloodPressure')
                                 for e in route['patient_record']['extension']))
            self.assertNotIn(full_name, json.dumps(route))
            self.assertNotIn('TEST-PHONE', json.dumps(route))
            self.assertNotIn('1990-01-01', json.dumps(route))
            ReferralRequestSchema.model_validate(route)
            invalid = copy.deepcopy(route)
            invalid['patient_record']['birthDate'] = '1990-01-01'
            with self.assertRaises(ValidationError):
                ReferralRequestSchema.model_validate(invalid)
            invalid = copy.deepcopy(route)
            invalid['diagnosis_concept']['coding'][0]['code'] = '25064002'
            next(e['resource'] for e in invalid['clinical_bundle']['entry'] if e['resource']['resourceType']=='Condition')['code']['coding'][0]['code']='25064002'
            code, rejected = request('POST', '/api/v1/referral/initiate', source, invalid)
            self.assertEqual(code, 422, rejected)
            invalid = copy.deepcopy(route)
            invalid['chief_complaint_concept']['coding'][0]['code'] = '233604007'
            next(e['resource'] for e in invalid['clinical_bundle']['entry'] if e['resource']['resourceType']=='Encounter')['reasonCode'][0]['coding'][0]['code']='233604007'
            code, rejected = request('POST', '/api/v1/referral/initiate', source, invalid)
            self.assertEqual(code, 422, rejected)
            code, created = request('POST', '/api/v1/referral/initiate', source, route)
            self.assertEqual(code, 200, created)
            referral_id = created['referral_id']
            self.assertFalse((vault_root / (referral_id + '.identity')).exists())
            with engine.begin() as connection:
                row = connection.execute(text('SELECT patient_id, patient_full_name, patient_dob, patient_phone, '
                    'diagnosis_system, diagnosis_code, diagnosis_display, diagnosis_text, '
                    'chief_complaint_system, chief_complaint_code, chief_complaint_display, chief_complaint_text, '
                    'triage_code, referral_priority, condition_severity_code '
                    'FROM referrals WHERE referral_id = :rid'), {'rid': referral_id}).mappings().one()
                patient_id = row['patient_id']
                self.assertEqual(aes_decrypt(patient_id), transfer_id)
                self.assertIsNone(row['patient_full_name'])
                self.assertIsNone(row['patient_dob'])
                self.assertIsNone(row['patient_phone'])
                self.assertEqual(row['diagnosis_code'], '233604007')
                self.assertEqual(row['diagnosis_display'], 'Pneumonia')
                self.assertEqual(row['diagnosis_text'], 'Possible pneumonia, right lung')
                self.assertEqual(row['diagnosis_system'], 'http://snomed.info/sct')
                self.assertEqual(row['chief_complaint_code'], '29857009')
                self.assertEqual(row['chief_complaint_display'], 'Chest pain')
                self.assertEqual(row['chief_complaint_text'], 'Severe chest pain radiating to the left arm')
                self.assertEqual(row['triage_code'], '1')
                self.assertEqual(row['referral_priority'], 'urgent')
                self.assertEqual(row['condition_severity_code'], '24484000')
                audit = connection.execute(text('SELECT previous_values, new_values, reason FROM referral_urgency_audits '
                    'WHERE referral_id = :rid'), {'rid': referral_id}).mappings().one()
                self.assertEqual(audit['previous_values']['suggested_priority'], 'routine')
                self.assertEqual(audit['new_values']['referral_priority'], 'urgent')
                self.assertEqual(audit['reason'], 'Synthetic doctor override')
                observations=connection.execute(text('SELECT loinc_code, unit_code, value_numeric FROM referral_observations WHERE referral_id=:rid'), {'rid':referral_id}).mappings().all()
                self.assertEqual(len(observations),8)
                self.assertEqual({r['loinc_code'] for r in observations},{'8480-6','8462-4','8867-4','9279-1','8310-5','2708-6','8302-2','29463-7'})
            code, bundle=request('GET',f'/api/v1/referral/{referral_id}/clinical-bundle',source)
            self.assertEqual(code,200,bundle)
            condition=next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType']=='Condition')
            self.assertEqual(condition['code']['coding'][0]['display'],'Pneumonia')
            code, forbidden_bundle=request('GET',f'/api/v1/referral/{referral_id}/clinical-bundle',recipient)
            self.assertEqual(code,403,forbidden_bundle)
            code, mine = request('GET', '/api/v1/referral/mine', source)
            self.assertEqual(code, 200, mine)
            self.assertEqual(next(r for r in mine if r['referral_id'] == referral_id)['diagnosis_code'], '233604007')
            code, denied = request('GET', f'/api/v1/referral/{referral_id}/patient-details', recipient)
            self.assertEqual(code, 403, denied)
            # Set the finalized destination on our test fixture without changing facility load counters.
            with engine.begin() as connection:
                connection.execute(text('UPDATE referrals SET receiving_facility = :name, status = :status '
                    'WHERE referral_id = :rid'), {'name': recipient['name'], 'status': 'ACCEPTED', 'rid': referral_id})
            code, details = request('GET', f'/api/v1/referral/{referral_id}/patient-details', recipient)
            self.assertEqual(code, 200, details)
            self.assertIsNone(details['full_name'])
            self.assertIn('patient_transfer', details)
            opened = php({'action': 'fetch', 'details': details, 'facility_id': recipient['local_facility_id']})
            self.assertEqual(opened['full_name'], full_name)
            self.assertEqual(opened['phone'], 'TEST-PHONE')
            self.assertEqual(opened['middle_name'], 'Transfer')
            self.assertEqual(opened['_source'], 'direct-hospital')
            self.assertNotIn('patient_transfer', opened)
            self.assertEqual(opened['diagnosis_code'], '233604007')
            self.assertEqual(opened['diagnosis_text'], 'Possible pneumonia, right lung')
            self.assertEqual(opened['chief_complaint_code'], '29857009')
            self.assertEqual(opened['chief_complaint_text'], 'Severe chest pain radiating to the left arm')
            self.assertEqual(opened['triage_code'], '1')
            self.assertEqual(len(opened['observations']),8)
            reassessment = {'triage': {'system': 'https://irdss.gov.ph/fhir/CodeSystem/triage-acuity', 'code': '4'},
                'referral_priority': 'asap', 'clinical_actor': {'user_id': 'synthetic-receiver', 'role': 'DOCTOR'},
                'condition_severity': {'system': 'http://snomed.info/sct', 'code': '6736007'},
                'reason': 'Synthetic receiving-clinician reassessment'}
            code, denied = request('PATCH', f'/api/v1/referral/{referral_id}/clinical-urgency', source, reassessment)
            self.assertEqual(code, 403, denied)
            code, updated = request('PATCH', f'/api/v1/referral/{referral_id}/clinical-urgency', recipient, reassessment)
            self.assertEqual(code, 200, updated)
            self.assertEqual(updated['triage_code'], '4')
            with engine.begin() as connection:
                audit = connection.execute(text('SELECT previous_values, new_values, actor_user_id FROM referral_urgency_audits '
                    'WHERE referral_id = :rid AND event_type = :event'), {'rid': referral_id, 'event': 'REASSESSMENT'}).mappings().one()
                self.assertEqual(audit['previous_values']['triage_code'], '1')
                self.assertEqual(audit['new_values']['triage_code'], '4')
                self.assertEqual(audit['actor_user_id'], 'synthetic-receiver')
            code,bundle=request('GET',f'/api/v1/referral/{referral_id}/clinical-bundle',recipient)
            self.assertEqual(next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType']=='ServiceRequest')['priority'],'asap')
            self.assertEqual(next(e['resource'] for e in bundle['entry'] if e['resource']['resourceType']=='Condition')['severity']['coding'][0]['code'],'6736007')
            arrival={'vital_bp':'118/78','vital_hr':'70','vital_rr':'16','vital_temp_c':'36.6','vital_o2sat':'99','vital_height_cm':'170','vital_weight_kg':'65',
                'observed_at':datetime.now(timezone.utc).isoformat(),'oxygen_method':'pulse-oximetry'}
            code,arrived=request('PATCH',f'/api/v1/referral/{referral_id}/arrive',recipient,arrival)
            self.assertEqual(code,200,arrived)
            code,repeated=request('PATCH',f'/api/v1/referral/{referral_id}/arrive',recipient,{'vital_hr':'90'})
            self.assertEqual(code,200,repeated)
            with engine.begin() as connection:
                rows=connection.execute(text('SELECT loinc_code, measurement_context, value_numeric FROM referral_observations WHERE referral_id=:rid'),{'rid':referral_id}).mappings().all()
                self.assertEqual(len(rows),16)
                self.assertEqual(next(r['value_numeric'] for r in rows if r['loinc_code']=='8867-4' and r['measurement_context']=='referral'),72)
                self.assertEqual(next(r['value_numeric'] for r in rows if r['loinc_code']=='8867-4' and r['measurement_context']=='arrival'),70)
            wrong = php({'action': 'fetch', 'details': details, 'facility_id': source['local_facility_id']}, True)
            self.assertIn('error', wrong)
            ticket = details['patient_transfer']['ticket']
            self.assertEqual(php({'action': 'verify', 'ticket': ticket})['referral_id'], referral_id)
            self.assertIn('error', php({'action': 'verify', 'ticket': ticket[:-8] + 'AAAAAAAA'}, True))
            expired = None
            with patch('app.services.direct_patient_transfer.time.time', return_value=time.time() - 120):
                expired = issue_ticket(referral_id, transfer_id, source_code, recipient_code)['ticket']
            with self.assertRaises(ValueError):
                verify_ticket(expired)
            self.assertIn('error', php({'action': 'verify', 'ticket': expired}, True))
            # Changing the selected destination invalidates an otherwise authentic ticket.
            with engine.begin() as connection:
                connection.execute(text('UPDATE referrals SET receiving_facility = NULL WHERE referral_id = :rid'),
                                   {'rid': referral_id})
            self.assertIn('error', php({'action': 'fetch', 'details': details,
                                      'facility_id': recipient['local_facility_id']}, True))
        finally:
            php({'action': 'cleanup', 'transfer_id': transfer_id})
            if referral_id:
                with engine.begin() as connection:
                    for table in ('referral_responses', 'referral_reasons', 'referrals'):
                        connection.execute(text(f'DELETE FROM {table} WHERE referral_id = :rid'), {'rid': referral_id})
                    if patient_id:
                        connection.execute(text('DELETE FROM patient_record WHERE fhir_id = :pid'), {'pid': patient_id})


if __name__ == '__main__':
    unittest.main()
