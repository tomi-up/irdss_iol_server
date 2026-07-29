import sys
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database.db_connection import Base, get_db
from app.database.seed_hospitals import seed_hospitals_and_keys
from app.utils.security import settings, hash_api_key

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

def run_all_tests():
    print("Setting up test database and seeding initial hospitals...")
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    seeded = seed_hospitals_and_keys(db)
    db.close()

    st_jude_key = None
    city_care_key = None
    for item in seeded:
        if item["hospital_name"] == "St. Jude General Hospital":
            st_jude_key = item["raw_api_key"]
            st_jude_id = item["hospital_id"]
        elif item["hospital_name"] == "City Care Medical Center":
            city_care_key = item["raw_api_key"]
            city_care_id = item["hospital_id"]

    assert st_jude_key is not None and city_care_key is not None

    print("\n--- Test 1: Unauthorized Access ---")
    res = client.get("/api/v1/hospitals/me/inventory")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("PASS: Request without API key blocked with 401 Unauthorized.")

    print("\n--- Test 2: Auto-identify & Retrieve My Inventory (/me/inventory) ---")
    headers_stjude = {"X-API-Key": st_jude_key}
    res = client.get("/api/v1/hospitals/me/inventory", headers=headers_stjude)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json()["hospital_name"] == "St. Jude General Hospital"
    print("PASS: St. Jude API key auto-retrieved St. Jude inventory.")

    print("\n--- Test 3: Update Own Inventory via /me/inventory ---")
    patch_payload = {"available_beds": 125, "medical_specialists_count": 34}
    res = client.patch("/api/v1/hospitals/me/inventory", headers=headers_stjude, json=patch_payload)
    assert res.status_code == 200
    assert res.json()["hospital"]["available_beds"] == 125
    print("PASS: St. Jude updated its own inventory successfully.")

    print("\n--- Test 4: Access Control Enforced (403 Forbidden for Other Hospital's ID) ---")
    # St. Jude key trying to modify City Care (id: city_care_id)
    forbidden_res = client.patch(f"/api/v1/hospitals/{city_care_id}/inventory", headers=headers_stjude, json={"available_beds": 1})
    assert forbidden_res.status_code == 403, f"Expected 403, got {forbidden_res.status_code}"
    assert "Forbidden" in forbidden_res.json()["detail"]
    print("PASS: St. Jude API Key blocked from modifying City Care records (403 Forbidden).")

    print("\n--- Test 5: City Care Updating Its Own Inventory ---")
    headers_citycare = {"X-API-Key": city_care_key}
    city_res = client.patch(f"/api/v1/hospitals/{city_care_id}/inventory", headers=headers_citycare, json={"available_beds": 88})
    assert city_res.status_code == 200
    assert city_res.json()["hospital"]["hospital_name"] == "City Care Medical Center"
    assert city_res.json()["hospital"]["available_beds"] == 88
    print("PASS: City Care Medical Center updated its own record successfully.")

    print("\nALL MULTI-TENANT AUTHORIZATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_all_tests()
