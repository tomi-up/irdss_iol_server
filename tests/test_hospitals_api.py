import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db_connection import Base, get_db
from app.utils.security import settings

# Create in-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
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


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)
VALID_API_KEY = settings.API_KEY


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


def test_unauthorized_access():
    """Verify that requests without valid X-API-Key are rejected with 401."""
    response = client.get("/api/v1/hospitals")
    assert response.status_code == 401
    assert "Invalid or missing API Key" in response.json()["detail"]

    response = client.post(
        "/api/v1/hospitals/register",
        headers={"X-API-Key": "wrong-key"},
        json={"name": "Test Hospital"}
    )
    assert response.status_code == 401


def test_register_hospital_fhir():
    """Verify creating a new hospital record with FHIR Location payload."""
    headers = {"X-API-Key": VALID_API_KEY}
    payload = {
        "resourceType": "Location",
        "id": "HOSP-SPMC-001",
        "name": "Southern Philippines Medical Center",
        "status": "active",
        "position": {
            "latitude": 7.0731,
            "longitude": 125.6128
        },
        "extension": [
            {
                "url": "http://irdss.gov.ph/fhir/StructureDefinition/hospital_level",
                "valueString": "Level 3"
            },
            {
                "url": "http://irdss.gov.ph/fhir/StructureDefinition/hospital_environment",
                "valueString": "Urban"
            },
            {
                "url": "http://irdss.gov.ph/fhir/StructureDefinition/available_beds",
                "valueInteger": 120
            },
            {
                "url": "http://irdss.gov.ph/fhir/StructureDefinition/emergency_equipment",
                "valueBoolean": True
            },
            {
                "url": "http://irdss.gov.ph/fhir/StructureDefinition/medical_equipment",
                "valueBoolean": True
            },
            {
                "url": "http://irdss.gov.ph/fhir/StructureDefinition/communication_systems",
                "valueBoolean": True
            },
            {
                "url": "http://irdss.gov.ph/fhir/StructureDefinition/medical_specialists_count",
                "valueInteger": 35
            }
        ]
    }

    response = client.post("/api/v1/hospitals/register", headers=headers, json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "success"
    assert data["hospital"]["hospital_name"] == "Southern Philippines Medical Center"
    assert data["hospital"]["available_beds"] == 120
    assert data["hospital"]["medical_specialists_count"] == 35
    assert data["hospital"]["emergency_equipment"] is True


def test_update_hospital_fhir_and_patch():
    """Verify updating hospital records via PUT (FHIR) and PATCH (Inventory)."""
    headers = {"X-API-Key": VALID_API_KEY}
    
    # 1. First register a hospital
    register_payload = {
        "resourceType": "Location",
        "name": "Davao Regional Medical Center",
        "position": {"latitude": 7.4475, "longitude": 125.8088},
        "extension": [
            {"url": "available_beds", "valueInteger": 50},
            {"url": "medical_specialists_count", "valueInteger": 15}
        ]
    }
    res = client.post("/api/v1/hospitals/register", headers=headers, json=register_payload)
    assert res.status_code == 201
    h_id = res.json()["hospital"]["id"]

    # 2. Update via PUT (FHIR)
    update_payload = {
        "resourceType": "Location",
        "name": "Davao Regional Medical Center (Main)",
        "position": {"latitude": 7.4475, "longitude": 125.8088},
        "extension": [
            {"url": "available_beds", "valueInteger": 80},
            {"url": "medical_specialists_count", "valueInteger": 25},
            {"url": "emergency_equipment", "valueBoolean": True}
        ]
    }
    put_res = client.put(f"/api/v1/hospitals/{h_id}", headers=headers, json=update_payload)
    assert put_res.status_code == 200
    assert put_res.json()["hospital"]["hospital_name"] == "Davao Regional Medical Center (Main)"
    assert put_res.json()["hospital"]["available_beds"] == 80

    # 3. Patch specific inventory metrics
    patch_payload = {
        "available_beds": 45,
        "medical_specialists_count": 30
    }
    patch_res = client.patch(f"/api/v1/hospitals/{h_id}/inventory", headers=headers, json=patch_payload)
    assert patch_res.status_code == 200
    assert patch_res.json()["hospital"]["available_beds"] == 45
    assert patch_res.json()["hospital"]["medical_specialists_count"] == 30

    # 4. Get hospital details
    get_res = client.get(f"/api/v1/hospitals/{h_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == h_id
    assert get_res.json()["available_beds"] == 45

    # 5. List hospitals
    list_res = client.get("/api/v1/hospitals", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1
