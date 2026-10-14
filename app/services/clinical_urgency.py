"""IRDSS prototype urgency rules: triage is not condition severity."""
import json
from pathlib import Path
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[2] / 'terminology'

def urgency_policy():
    triage = json.loads((ROOT / 'CodeSystem-irdss-triage-acuity.json').read_text(encoding='utf8'))
    mapping = json.loads((ROOT / 'ConceptMap-irdss-triage-to-request-priority.json').read_text(encoding='utf8'))
    condition = json.loads((ROOT / 'snapshots/ValueSet-fhir-condition-severity-4.0.1.json').read_text(encoding='utf8'))
    return triage, {e['code']: e['target'][0]['code'] for e in mapping['group'][0]['element']}, condition['compose']['include'][0]

def resolve_urgency(payload, legacy_level=None):
    triage, mapping, condition = urgency_policy()
    labels = {c['code']: c['display'] for c in triage['concept']}
    coding = payload.triage
    code = coding.code if coding else str(legacy_level)
    if code not in labels or (coding and coding.system != triage['url']):
        raise HTTPException(422, 'A valid IRDSS triage acuity (1–5) is required.')
    if coding and (not payload.clinical_actor or payload.clinical_actor.role != 'DOCTOR'):
        raise HTTPException(403, 'A doctor must assign or reassess triage acuity.')
    if coding and legacy_level not in (None, 0, int(code)):
        raise HTTPException(422, 'Legacy severity must agree with triage acuity.')
    priority = payload.referral_priority or mapping[code]
    reason = (payload.priority_override_reason or '').strip()
    if priority != mapping[code] and not reason:
        raise HTTPException(422, 'A reason is required when overriding the suggested referral priority.')
    cc = payload.condition_severity
    condition_labels = {c['code']: c['display'] for c in condition['concept']}
    if cc and (cc.system != condition['system'] or cc.code not in condition_labels):
        raise HTTPException(422, 'Invalid condition severity coding.')
    return {'triage_system': triage['url'], 'triage_code': code, 'triage_display': labels[code],
        'referral_priority': priority, 'condition_severity_system': cc.system if cc else None,
        'condition_severity_code': cc.code if cc else None,
        'condition_severity_display': condition_labels[cc.code] if cc else None}

def urgency_fields(referral):
    return {k: getattr(referral, k, None) for k in ('triage_system', 'triage_code', 'triage_display',
        'referral_priority', 'condition_severity_system', 'condition_severity_code', 'condition_severity_display')}
