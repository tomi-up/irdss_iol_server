import copy
import unittest
from datetime import datetime, timezone
from fastapi import HTTPException
from app.schemas.encounter import ReferralRequestSchema
from app.services.fhir_clinical import parse_clinical_bundle
from tests.test_direct_patient_transfer import php

def clinical_fixture(diagnosis=True):
    token='tx_'+'a'*32
    payload={'resourceType':'Encounter','status':'planned','subject':{'reference':'Patient/'+token},
        'patient_record':{'resourceType':'Patient','id':token,'name':[],'gender':'male','extension':[]},
        'identity_mode':'DIRECT','patient_token':'f'*64,'age_years':30,'age_months':360,'age_days':11000,
        'reasonCode':[{'text':'Service unavailable'}], 'triage':{'system':'https://irdss.gov.ph/fhir/CodeSystem/triage-acuity','code':'1'},
        'referral_priority':'routine','clinical_actor':{'user_id':'test-doctor','role':'DOCTOR'},
        'diagnosis_concept':{'text':'Possible pneumonia','coding':[{'system':'http://snomed.info/sct','code':'233604007','display':'Pneumonia'}]} if diagnosis else {},
        'chief_complaint_concept':{'text':'Cough for two days','coding':[{'system':'http://snomed.info/sct','code':'49727002','display':'Cough'}]}}
    user={'id':'test-doctor','facility':{'name':'Synthetic Hospital','code':'TEST-FACILITY'}}
    vitals={'vital_bp':'120/80','vital_hr':'72','vital_rr':'18','vital_temp_c':'36.5','vital_o2sat':'98','vital_height_cm':'170','vital_weight_kg':'65'}
    payload['clinical_bundle']=php({'action':'build-clinical','payload':payload,'user':user,'vitals':vitals,
        'observed_at':datetime.now(timezone.utc).isoformat(),'oxygen_method':'pulse-oximetry'})
    return payload

class FhirClinicalTests(unittest.TestCase):
    def test_linked_condition_service_request_and_seven_observations(self):
        payload=ReferralRequestSchema.model_validate(clinical_fixture())
        facts=parse_clinical_bundle(payload,'Synthetic Hospital')
        self.assertEqual(len(facts['observations']),8)
        self.assertEqual(facts['vitals']['vital_bp'],'120/80')
        self.assertEqual(facts['vitals']['vital_temp_c'],'36.5')
        self.assertEqual(payload.diagnosis_concept.coding[0].code,'233604007')
        self.assertEqual(payload.chief_complaint_concept.text,'Cough for two days')
        self.assertEqual(facts['request']['priority'],'routine')
        self.assertEqual({r['loinc_code'] for r in facts['observations']}, {'8480-6','8462-4','8867-4','9279-1','8310-5','2708-6','8302-2','29463-7'})
        oxygen=next(e['resource'] for e in facts['entries'] if e['resource']['resourceType']=='Observation' and e['resource']['code']['coding'][0]['code']=='2708-6')
        self.assertEqual(oxygen['code']['coding'][1]['code'],'59408-5')

    def test_absent_diagnosis_does_not_invent_condition(self):
        facts=parse_clinical_bundle(ReferralRequestSchema.model_validate(clinical_fixture(False)),'Synthetic Hospital')
        self.assertIsNone(facts['condition'])
        self.assertNotIn('reasonReference',facts['request'])

    def test_invalid_units_references_and_identity_rejected(self):
        fixture=clinical_fixture()
        for change in ('unit','reference','identity','timestamp','duplicate'):
            data=copy.deepcopy(fixture); entries=data['clinical_bundle']['entry']
            observation=next(e['resource'] for e in entries if e['resource']['resourceType']=='Observation' and 'valueQuantity' in e['resource'])
            if change=='unit': observation['valueQuantity']['code']='Cel'
            if change=='reference': observation['subject']['reference']='urn:uuid:missing'
            if change=='identity': entries[0]['resource']['name']=[{'text':'Patient Name'}]
            if change=='timestamp': observation['effectiveDateTime']='2050-01-01T00:00:00Z'
            if change=='duplicate': entries.append(copy.deepcopy(entries[-1]))
            with self.subTest(change=change), self.assertRaises(HTTPException) as caught:
                parse_clinical_bundle(ReferralRequestSchema.model_validate(data),'Synthetic Hospital')
            self.assertEqual(caught.exception.status_code,422)

    def test_each_measurement_keeps_its_time_and_zero_values(self):
        data=clinical_fixture(); patient=data['clinical_bundle']['entry'][0]['resource']
        user={'id':'test-doctor','facility':{'name':'Synthetic Hospital','code':'TEST-FACILITY'}}
        data['clinical_bundle']=php({'action':'build-clinical','payload':data,'user':user,
            'vitals':{'vital_hr':'0','vital_o2sat':'0'},'observed_at':datetime.now(timezone.utc).isoformat(),
            'timestamps':{'vital_hr':'2026-10-01T12:00:00+08:00'}})
        facts=parse_clinical_bundle(ReferralRequestSchema.model_validate(data),'Synthetic Hospital')
        self.assertEqual(facts['vitals']['vital_hr'],'0')
        self.assertEqual(facts['observations'][0]['observed_at'].isoformat(),'2026-10-01T04:00:00+00:00')
