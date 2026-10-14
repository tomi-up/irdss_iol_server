"""Supported Phase 7/8 clinical subset, not a general FHIR transaction server."""
import copy
import json
import math
import re
from decimal import Decimal
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import HTTPException
from app.schemas.encounter import DiagnosisConcept, ChiefComplaintConcept, DiagnosisCoding, FHIRReasonCode
from app.models.referral_model import ReferralObservation
from app.models.referral_clinical_resource import ReferralClinicalResource

DEFINITIONS = json.loads((Path(__file__).resolve().parents[2]/'terminology/vital-signs.json').read_text(encoding='utf8'))
ALLOWED = {
    'Patient': {'resourceType','id','identifier','gender'},
    'Organization': {'resourceType','id','identifier','name'},
    'PractitionerRole': {'resourceType','id','identifier','organization','code'},
    'Encounter': {'resourceType','id','status','class','subject','serviceProvider','reasonCode'},
    'Condition': {'resourceType','id','subject','encounter','clinicalStatus','verificationStatus','category','code','severity'},
    'ServiceRequest': {'resourceType','id','status','intent','priority','subject','encounter','requester','code','reasonCode','reasonReference','supportingInfo','authoredOn'},
    'Observation': {'resourceType','id','status','category','code','subject','encounter','effectiveDateTime','valueQuantity','component'},
}

def require(condition, message):
    if not condition: raise HTTPException(422, message)

def measurement_time(value):
    try:
        time = datetime.fromisoformat(value.replace('Z','+00:00')) if isinstance(value,str) else value
        require(isinstance(time,datetime) and time.tzinfo is not None, 'Observation measurement time requires a timezone.')
        require(time <= datetime.now(timezone.utc)+timedelta(minutes=5), 'Observation measurement time is in the future.')
        return time.astimezone(timezone.utc)
    except (TypeError,ValueError,AttributeError) as exc:
        raise HTTPException(422, 'Invalid Observation measurement time.') from exc

def concept(value):
    require(isinstance(value,dict) and set(value) <= {'coding','text'}, 'Invalid clinical CodeableConcept.')
    require(isinstance(value.get('coding',[]),list) and len(value.get('coding',[]))<=16, 'Invalid clinical coding list.')
    for coding in value.get('coding',[]):
        require(isinstance(coding,dict) and set(coding) <= {'system','code','display'}, 'Invalid clinical Coding.')
        DiagnosisCoding.model_validate(coding)
    require(value.get('text') is None or isinstance(value['text'],str) and len(value['text'])<=2000, 'Invalid clinical narrative.')
    return {k:v for k,v in value.items() if v is not None}

def code(value):
    value = concept(value)
    coding = value.get('coding',[])
    require(bool(coding), 'A clinical code is required.')
    return coding[0]

def quantity(value, unit, field):
    require(isinstance(value,dict) and set(value) <= {'value','unit','system','code'}, 'Invalid Observation quantity.')
    require(value.get('system') == 'http://unitsofmeasure.org' and value.get('code') == unit, 'Invalid UCUM unit for this measurement.')
    number = value.get('value')
    require(isinstance(number,(int,float)) and not isinstance(number,bool) and math.isfinite(number), 'Observation requires a finite numeric value.')
    require(0 <= number <= 1000000 and (field != 'vital_o2sat' or number <= 100), 'Observation value is outside the supported range.')
    require(Decimal(str(number))==Decimal(str(number)).quantize(Decimal('0.0001')), 'Observation supports up to four decimal places.')
    require(field not in ('vital_height_cm','vital_weight_kg') or number > 0, 'Height and weight must be positive.')
    return number

def observation_rows(resource, context='referral'):
    require(resource.get('status') == 'final', 'Vital-sign Observation status must be final.')
    category=code(resource['category'][0])
    require(category.get('system')=='http://terminology.hl7.org/CodeSystem/observation-category' and category.get('code')=='vital-signs', 'Observation requires the vital-signs category.')
    codings = resource['code']['coding']; primary = code(resource['code'])
    require(primary['system'] == 'http://loinc.org', 'Observation requires LOINC coding.')
    observed = measurement_time(resource['effectiveDateTime'])
    rows=[]; vital={}
    def append(coding, q, definition, field):
        number=quantity(q,definition['unit'],field)
        q['unit']=definition['unit_display']; coding['display']=definition['display']
        rows.append({'fhir_observation_id':resource['id'],'loinc_code':coding['code'], 'display':definition['display'],
            'value_numeric':number,'unit_code':definition['unit'],'unit_display':definition['unit_display'],
            'measurement_context':context,'observed_at':observed})
        return format(number,'.12g')
    if primary['code'] == '85354-9':
        resource['code']['coding'][0]['display']=DEFINITIONS['blood_pressure']['display']
        require('valueQuantity' not in resource and len(resource.get('component',[])) == 2 and len(codings)==1, 'Blood pressure requires exactly two components and no panel value.')
        by_code = {code(part['code'])['code']:part for part in resource['component']}
        require(set(by_code)=={'8480-6','8462-4'}, 'Blood pressure requires systolic and diastolic components.')
        values=[]
        for definition in DEFINITIONS['blood_pressure']['components']:
            part=by_code[definition['code']]; coding=code(part['code'])
            require(coding['system']=='http://loinc.org' and set(part)=={'code','valueQuantity'}, 'Invalid blood-pressure component.')
            values.append(append(coding,part['valueQuantity'],definition,'vital_bp'))
        vital['vital_bp']='/'.join(values)
    else:
        matches=[(field,d) for field,d in DEFINITIONS['measurements'].items() if d['code']==primary['code']]
        require(len(matches)==1 and 'component' not in resource, 'Unsupported vital-sign LOINC code.')
        field,definition=matches[0]
        allowed_codes={primary['code']} | ({'59408-5'} if field=='vital_o2sat' else set())
        require(all(c.get('system')=='http://loinc.org' and c.get('code') in allowed_codes for c in codings), 'Unsupported additional Observation coding.')
        for c in resource['code']['coding']:
            c['display']=definition['display'] if c['code']==primary['code'] else DEFINITIONS['pulse_oximetry']['display']
        vital[field]=append(primary,resource['valueQuantity'],definition,field)
    return rows,vital

def parse_clinical_bundle(payload, hospital):
    if payload.clinical_bundle is None: return None
    try:
        bundle=copy.deepcopy(payload.clinical_bundle)
        require(set(bundle) <= {'resourceType','type','entry'} and bundle.get('resourceType')=='Bundle' and bundle.get('type')=='transaction', 'Clinical Bundle must be a transaction Bundle.')
        entries=bundle['entry']; require(isinstance(entries,list) and 5<=len(entries)<=20, 'Clinical Bundle resource count is invalid.')
        indexed={}; grouped={}
        for entry in entries:
            require(set(entry)=={'fullUrl','resource','request'}, 'Invalid clinical Bundle entry.')
            resource=entry['resource']; rt=resource.get('resourceType'); url=entry['fullUrl']
            require(rt in ALLOWED and set(resource)<=ALLOWED[rt], 'Unsupported clinical resource fields; direct identifiers are not allowed.')
            require(url=='urn:uuid:'+resource['id'] and str(uuid.UUID(resource['id']))==resource['id'], 'Clinical resources require Bundle-local UUID references.')
            require(url not in indexed and entry['request']=={'method':'POST','url':rt}, 'Duplicate or invalid clinical Bundle request.')
            indexed[url]=resource; grouped.setdefault(rt,[]).append(resource)
        for rt in ('Patient','Organization','PractitionerRole','Encounter','ServiceRequest'):
            require(len(grouped.get(rt,[]))==1, f'Clinical Bundle requires one {rt}.')
        require(len(grouped.get('Condition',[]))<=1, 'Only one working-impression Condition is supported.')
        patient=grouped['Patient'][0]; organization=grouped['Organization'][0]; role=grouped['PractitionerRole'][0]
        encounter=grouped['Encounter'][0]; request=grouped['ServiceRequest'][0]
        patient_ref='urn:uuid:'+patient['id']; encounter_ref='urn:uuid:'+encounter['id']
        require(patient.get('identifier')==[{'system':'https://irdss.gov.ph/identifier/transfer','value':payload.patient_record.id}] and patient.get('gender')==payload.patient_record.gender, 'Clinical Patient must contain only the matching transfer identifier and gender.')
        require(patient['gender'] in ('male','female','other','unknown'), 'Unsupported FHIR Patient gender code.')
        require(organization.get('name')==hospital, 'Clinical Organization must match the authenticated sending facility.')
        identifiers=organization.get('identifier')
        require(isinstance(identifiers,list) and len(identifiers)==1 and set(identifiers[0])=={'system','value'}
            and identifiers[0]['system']=='https://irdss.gov.ph/identifier/local-facility'
            and isinstance(identifiers[0]['value'],str) and re.fullmatch(r'[A-Za-z0-9_.-]{1,100}',identifiers[0]['value']), 'Invalid sending facility identifier.')
        require(role.get('code')==[{'text':'Referring clinician'}], 'Invalid referring PractitionerRole code.')
        require(encounter.get('status')=='planned' and encounter.get('class')=={'system':'http://terminology.hl7.org/CodeSystem/v3-NullFlavor','code':'UNK'}, 'Invalid referral Encounter context.')
        def references(value):
            if isinstance(value,dict):
                if 'reference' in value:
                    require(set(value)=={'reference'} and value['reference'] in indexed, 'An internal clinical reference does not resolve.')
                for item in value.values(): references(item)
            elif isinstance(value,list):
                for item in value: references(item)
        for resource in indexed.values(): references(resource)
        require(role['organization']=={'reference':'urn:uuid:'+organization['id']} and encounter['serviceProvider']==role['organization'], 'Requester/facility references do not agree.')
        if payload.clinical_actor:
            require(role.get('identifier')==[{'system':'https://irdss.gov.ph/identifier/clinical-account','value':payload.clinical_actor.user_id}], 'PractitionerRole must identify the attested referring clinician.')
        for resource in grouped.get('Condition',[])+grouped.get('Observation',[])+[encounter,request]:
            require(resource.get('subject')=={'reference':patient_ref}, 'Clinical subject references do not agree.')
            if resource is not encounter: require(resource.get('encounter')=={'reference':encounter_ref}, 'Clinical Encounter references do not agree.')
        require(request.get('requester')=={'reference':'urn:uuid:'+role['id']} and request.get('status')=='active' and request.get('intent')=='order', 'Invalid referral ServiceRequest.')
        priority=request.get('priority'); require(priority in ('routine','urgent','asap','stat'), 'Invalid ServiceRequest priority.')
        require(payload.referral_priority in (None,priority), 'ServiceRequest priority conflicts with the routing envelope.')
        payload.referral_priority=priority
        require(len(encounter.get('reasonCode',[]))==1, 'Encounter requires the chief complaint narrative.')
        payload.chief_complaint_concept=ChiefComplaintConcept.model_validate(concept(encounter['reasonCode'][0]))
        reasons=request['reasonCode']; require(isinstance(reasons,list) and 1<=len(reasons)<=4, 'Invalid ServiceRequest referral reasons.')
        payload.reasonCode=[FHIRReasonCode.model_validate(concept(reason)) for reason in reasons]
        # Reuse the request schema's uniqueness/length safeguards after replacing legacy reasons.
        type(payload).validate_reason_codes(payload.reasonCode)
        condition=grouped.get('Condition',[None])[0]
        if condition:
            require(request.get('reasonReference')==[{'reference':'urn:uuid:'+condition['id']}], 'ServiceRequest must reference its Condition.')
            clinical_status=code(condition['clinicalStatus']); verification=code(condition['verificationStatus']); category=code(condition['category'][0])
            require(clinical_status.get('system')=='http://terminology.hl7.org/CodeSystem/condition-clinical' and clinical_status['code']=='active'
                and verification.get('system')=='http://terminology.hl7.org/CodeSystem/condition-ver-status' and verification['code']=='provisional', 'Working impression must be active and provisional.')
            require(category.get('system')=='http://terminology.hl7.org/CodeSystem/condition-category' and category['code']=='encounter-diagnosis', 'Working impression requires the encounter-diagnosis category.')
            payload.diagnosis_concept=DiagnosisConcept.model_validate(concept(condition['code']))
            require(bool(payload.diagnosis_concept.coding or (payload.diagnosis_concept.text or '').strip()), 'An empty diagnosis must not create a Condition.')
            payload.condition_severity=DiagnosisCoding.model_validate(code(condition['severity'])) if condition.get('severity') else None
        else:
            require(not request.get('reasonReference') and not payload.condition_severity, 'Absent diagnosis must not have a Condition reference or severity.')
            payload.diagnosis_concept=DiagnosisConcept()
        rows=[]; vitals={}
        expected_support=[]
        for obs in grouped.get('Observation',[]):
            normalized,values=observation_rows(obs)
            require(not (set(vitals)&set(values)), 'Duplicate referral-time vital measurement.')
            rows.extend(normalized); vitals.update(values); expected_support.append({'reference':'urn:uuid:'+obs['id']})
        require(request.get('supportingInfo',[])==expected_support, 'ServiceRequest supportingInfo must reference its vital Observations.')
        return {'entries':entries,'observations':rows,'vitals':vitals,'condition':condition,'request':request}
    except HTTPException: raise
    except (KeyError,TypeError,ValueError,AttributeError,IndexError) as exc:
        raise HTTPException(422, 'Invalid supported clinical FHIR Bundle structure.') from exc

def persist_resources(db, referral_id, entries, context='referral'):
    for entry in entries:
        r=entry['resource']
        db.add(ReferralClinicalResource(referral_id=referral_id, full_url=entry['fullUrl'], resource_type=r['resourceType'], measurement_context=context, resource=r))

def persist_observations(db, referral_id, rows):
    for row in rows: db.add(ReferralObservation(referral_id=referral_id, **row))

def resource_bundle(db, referral_id):
    resources=db.query(ReferralClinicalResource).filter(ReferralClinicalResource.referral_id==referral_id).order_by(ReferralClinicalResource.id).all()
    return {'resourceType':'Bundle','type':'collection','entry':[{'fullUrl':r.full_url,'resource':r.resource} for r in resources]}

def observation_details(db, referral_id):
    rows=db.query(ReferralObservation).filter(ReferralObservation.referral_id==referral_id).order_by(ReferralObservation.observed_at,ReferralObservation.id).all()
    return [{'fhir_observation_id':r.fhir_observation_id,'loinc_code':r.loinc_code,'display':r.display,
        'value':float(r.value_numeric) if r.value_numeric is not None else None,'unit':r.unit_code,'measurement_context':r.measurement_context,'observed_at':r.observed_at.isoformat() if r.observed_at else None} for r in rows]

def arrival_value_snapshot(records):
    fields={d['code']:field for field,d in DEFINITIONS['measurements'].items()}; result={}; bp={}
    for row in records:
        if row['measurement_context']!='arrival' or row['value'] is None: continue
        if row['loinc_code'] in fields: result['arrival_'+fields[row['loinc_code']]]=format(row['value'],'.12g')
        elif row['loinc_code'] in ('8480-6','8462-4'): bp[row['loinc_code']]=row
    if len(bp)==2 and bp['8480-6']['fhir_observation_id']==bp['8462-4']['fhir_observation_id']:
        result['arrival_vital_bp']='/'.join(format(bp[c]['value'],'.12g') for c in ('8480-6','8462-4'))
    return result

def arrival_clinical_resources(db, referral, values, observed_at, hospital, oxygen_method='unknown'):
    existing=resource_bundle(db,referral.referral_id)['entry']; entries=[]
    def add(resource):
        resource['id']=str(uuid.uuid4()); url='urn:uuid:'+resource['id']
        entries.append({'fullUrl':url,'resource':resource}); return url
    patient=next((entry['fullUrl'] for entry in existing if entry['resource']['resourceType']=='Patient'),None)
    if not patient:
        patient=add({'resourceType':'Patient','identifier':[{'system':'https://irdss.gov.ph/identifier/pseudonymous-patient','value':referral.patient_code}],
            'gender':referral.patient.gender if referral.patient else 'unknown'})
    organization=add({'resourceType':'Organization','name':hospital})
    encounter=add({'resourceType':'Encounter','status':'in-progress',
        'class':{'system':'http://terminology.hl7.org/CodeSystem/v3-NullFlavor','code':'UNK'},
        'subject':{'reference':patient},'serviceProvider':{'reference':organization}})
    timestamp=measurement_time(observed_at).isoformat(); rows=[]
    for field,value in values.items():
        if value is None or value=='': continue
        try:
            obs={'resourceType':'Observation','status':'final','category':[{'coding':[{'system':'http://terminology.hl7.org/CodeSystem/observation-category','code':'vital-signs'}]}],
                'subject':{'reference':patient},'encounter':{'reference':encounter},'effectiveDateTime':timestamp}
            if field=='vital_bp':
                numbers=value.split('/'); require(len(numbers)==2, 'Blood pressure requires two values.')
                obs['code']={'coding':[{'system':'http://loinc.org','code':'85354-9','display':DEFINITIONS['blood_pressure']['display']}]}
                obs['component']=[{'code':{'coding':[{'system':'http://loinc.org','code':d['code'],'display':d['display']}]},
                    'valueQuantity':{'value':float(numbers[i]),'system':'http://unitsofmeasure.org','code':d['unit'],'unit':d['unit_display']}}
                    for i,d in enumerate(DEFINITIONS['blood_pressure']['components'])]
            else:
                d=DEFINITIONS['measurements'][field]
                obs['code']={'coding':[{'system':'http://loinc.org','code':d['code'],'display':d['display']}]}
                if field=='vital_o2sat' and oxygen_method=='pulse-oximetry': obs['code']['coding'].append({'system':'http://loinc.org',**DEFINITIONS['pulse_oximetry']})
                obs['valueQuantity']={'value':float(value),'system':'http://unitsofmeasure.org','code':d['unit'],'unit':d['unit_display']}
            add(obs); normalized,_=observation_rows(obs,'arrival'); rows.extend(normalized)
        except HTTPException: raise
        except (ValueError,TypeError,KeyError) as exc: raise HTTPException(422,'Invalid arrival vital-sign value.') from exc
    return entries,rows

def sync_clinical_urgency(db,referral):
    resources=db.query(ReferralClinicalResource).filter(ReferralClinicalResource.referral_id==referral.referral_id).all()
    if resources and referral.condition_severity_code and not any(r.resource_type=='Condition' for r in resources):
        raise HTTPException(422,'A working-impression Condition is required before assigning condition severity.')
    for row in resources:
        value=copy.deepcopy(row.resource)
        if row.resource_type=='ServiceRequest': value['priority']=referral.referral_priority
        elif row.resource_type=='Condition':
            if referral.condition_severity_code: value['severity']={'coding':[{'system':referral.condition_severity_system,
                'code':referral.condition_severity_code,'display':referral.condition_severity_display}]}
            else: value.pop('severity',None)
        else: continue
        row.resource=value
