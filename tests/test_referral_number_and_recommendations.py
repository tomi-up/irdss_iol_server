import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db_connection import Base, get_db
from app.models.patient_model import PatientRecords
from app.models.referral_model import Referral
from app.routers.referral import get_current_hospital
from app.services.referral_number import (
    format_referral_number,
    next_referral_number,
    referral_number_period,
)

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client_as():
    """Returns a factory for a TestClient authenticated as the given hospital."""
    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = override_get_db

    def make(hospital_name):
        app.dependency_overrides[get_current_hospital] = lambda: hospital_name
        return TestClient(app)

    yield make
    app.dependency_overrides.clear()
    app.dependency_overrides.update(previous)


# ---------- referral number format and sequence ----------

def test_period_uses_philippine_time_at_month_boundary():
    # 16:30 UTC on Sept 30 is already 00:30 on Oct 1 in the Philippines
    assert referral_number_period(datetime(2026, 9, 30, 16, 30, tzinfo=timezone.utc)) == "202610"
    assert referral_number_period(datetime(2026, 9, 30, 15, 59, tzinfo=timezone.utc)) == "202609"


def test_format_is_zero_padded():
    assert format_referral_number("202610", 1) == "REF-202610-00001"
    assert format_referral_number("202610", 123456) == "REF-202610-123456"


def test_numbers_increment_within_a_month_and_reset_next_month(db):
    october = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)
    november = datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc)

    assert next_referral_number(db, october) == "REF-202610-00001"
    assert next_referral_number(db, october) == "REF-202610-00002"
    assert next_referral_number(db, november) == "REF-202611-00001"
    assert next_referral_number(db, october) == "REF-202610-00003"
    db.commit()


def test_rolled_back_referral_releases_its_number(db):
    now = datetime(2026, 10, 8, 4, 0, tzinfo=timezone.utc)
    assert next_referral_number(db, now) == "REF-202610-00001"
    db.rollback()
    assert next_referral_number(db, now) == "REF-202610-00001"


def test_current_number_matches_expected_shape(db):
    assert re.fullmatch(r"REF-\d{6}-\d{5,}", next_referral_number(db))


# ---------- /recommendations access control ----------

def _create_referral(db, referring_facility="Hospital A"):
    db.add(PatientRecords(fhir_id="patient-1"))
    referral = Referral(
        referral_id="ref_test000001",
        referral_number="REF-202610-00001",
        patient_id="patient-1",
        referring_facility=referring_facility,
        disease_severity="3",
    )
    db.add(referral)
    db.commit()
    return referral


def test_recommendations_require_authentication(db):
    _create_referral(db)
    app.dependency_overrides[get_db] = override_get_db
    try:
        response = TestClient(app).get("/api/v1/referral/ref_test000001/recommendations")
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert response.status_code == 401


def test_recommendations_reject_other_hospitals(db, client_as):
    _create_referral(db)
    response = client_as("Hospital B").get("/api/v1/referral/ref_test000001/recommendations")
    assert response.status_code == 403


def test_recommendations_return_404_for_unknown_referral(client_as):
    response = client_as("Hospital A").get("/api/v1/referral/ref_missing/recommendations")
    assert response.status_code == 404


def test_recommendations_allow_referring_hospital(db, client_as):
    _create_referral(db)
    response = client_as(" hospital a ").get("/api/v1/referral/ref_test000001/recommendations")
    assert response.status_code == 200
    assert response.json() == []
