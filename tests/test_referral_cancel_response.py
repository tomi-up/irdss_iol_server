"""Regression checks for stale receiver decisions; synthetic database fixtures only."""
import asyncio
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from app.database.db_connection import SessionLocal
from app.models.patient_model import PatientRecords
from app.models.referral_model import Referral
from app.models.referral_response_model import ReferralResponse
from app.schemas.encounter import ResponsePayloadSchema
from app.routers.referral import cancel_referral, respond_to_referral


class CancelResponseTests(unittest.TestCase):
    def setUp(self):
        self.rid = 'ref_test_' + uuid.uuid4().hex[:12]
        self.pid = 'test_cancel_' + uuid.uuid4().hex
        with SessionLocal() as db:
            db.add(PatientRecords(fhir_id=self.pid))
            db.flush()
            db.add(Referral(referral_id=self.rid, patient_id=self.pid,
                            referring_facility='Synthetic Sender', disease_severity='1', status='CREATED'))
            db.flush()
            db.add(ReferralResponse(referral_id=self.rid, hospital_name='Synthetic Receiver', response_status='PENDING'))
            db.commit()
        self.broadcast = patch('app.routers.referral.manager.broadcast_to_facility', new_callable=AsyncMock)
        self.broadcast.start()

    def tearDown(self):
        self.broadcast.stop()
        with SessionLocal() as db:
            db.query(ReferralResponse).filter_by(referral_id=self.rid).delete()
            db.query(Referral).filter_by(referral_id=self.rid).delete()
            db.query(PatientRecords).filter_by(fhir_id=self.pid).delete()
            db.commit()

    def respond(self, decision='ACCEPTED'):
        with SessionLocal() as db:
            body = {'decision': decision}
            if decision == 'REDIRECTED': body['redirect_reason_code'] = 'NO_AVAILABLE_BED'
            return asyncio.run(respond_to_referral(self.rid, ResponsePayloadSchema(**body), db, 'Synthetic Receiver'))

    def cancel(self):
        with SessionLocal() as db:
            return asyncio.run(cancel_referral(self.rid, db, 'Synthetic Sender'))

    def assertCancelled(self):
        with SessionLocal() as db:
            self.assertEqual(db.query(Referral).filter_by(referral_id=self.rid).one().status, 'CANCELLED')
            alert = db.query(ReferralResponse).filter_by(referral_id=self.rid).one()
            self.assertEqual(alert.response_status, 'CANCELLED')
            self.assertIsNone(alert.responded_at)

    def test_opened_then_cancelled_cannot_accept_or_redirect(self):
        self.cancel()
        for decision in ('ACCEPTED', 'REDIRECTED'):
            with self.assertRaises(HTTPException) as error: self.respond(decision)
            self.assertEqual(error.exception.status_code, 409)
            self.assertIn('referring hospital cancelled', error.exception.detail)
        self.assertCancelled()

    def test_accept_first_blocks_cancellation_and_duplicate_decision(self):
        self.assertEqual(self.respond()['status'], 'success')
        with self.assertRaises(HTTPException) as error: self.cancel()
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(HTTPException) as error: self.respond()
        self.assertEqual(error.exception.status_code, 409)
        with SessionLocal() as db:
            self.assertEqual(db.query(ReferralResponse).filter_by(referral_id=self.rid).one().response_status, 'ACCEPTED')

    def test_response_waits_for_cancellation_transaction(self):
        # Keep cancellation uncommitted while a receiver tries to accept.
        started = Event()
        def receiver():
            started.set()
            try: self.respond()
            except HTTPException as error: return error.status_code, error.detail
            return 200, 'accepted'
        with ThreadPoolExecutor(max_workers=1) as pool, SessionLocal() as db:
            referral = db.query(Referral).filter_by(referral_id=self.rid).with_for_update().one()
            referral.status = 'CANCELLED'
            db.query(ReferralResponse).filter_by(referral_id=self.rid).update({'response_status':'CANCELLED'})
            attempt = pool.submit(receiver)
            self.assertTrue(started.wait(5))
            db.commit()
            code, detail = attempt.result(timeout=10)
            self.assertEqual(code, 409)
            self.assertIn('referring hospital cancelled', detail)
        self.assertCancelled()

    def test_missing_referral_does_not_return_success(self):
        with SessionLocal() as db:
            db.query(ReferralResponse).filter_by(referral_id=self.rid).delete()
            db.query(Referral).filter_by(referral_id=self.rid).delete()
            db.commit()
        with self.assertRaises(HTTPException) as error: self.respond()
        self.assertEqual(error.exception.status_code, 404)

    def test_signed_http_cancel_then_accept_returns_conflict(self):
        from app.services.direct_patient_transfer import directory
        from tests.test_direct_patient_transfer import request
        facilities = list(directory().values())
        source, recipient = facilities[0], facilities[1]
        with SessionLocal() as db:
            db.query(Referral).filter_by(referral_id=self.rid).update({'referring_facility':source['name']})
            db.query(ReferralResponse).filter_by(referral_id=self.rid).update({'hospital_name':recipient['name']})
            db.commit()
        code, result = request('PATCH', f'/api/v1/referral/{self.rid}/cancel', source)
        self.assertEqual(code, 200, result)
        code, result = request('PATCH', f'/api/v1/referral/{self.rid}/respond', recipient, {'decision':'ACCEPTED'})
        self.assertEqual(code, 409, result)
        self.assertEqual(result['detail'], 'Unable to accept. The referring hospital cancelled this referral.')
        self.assertCancelled()
