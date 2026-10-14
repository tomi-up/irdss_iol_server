import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    print("Setting up test database and seeding initial health facilities...")
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    seeded = seed_hospitals_and_keys(db)
    db.close()

    st_jude_key = None
    city_care_key = None
    st_jude_id = None
    city_care_id = None

    for item in seeded:
        if item["facility_name"] == "St. Jude General Hospital":
            st_jude_key = item["raw_api_key"]
            st_jude_id = item["facility_id"]
        elif item["facility_name"] == "City Care Medical Center":
            city_care_key = item["raw_api_key"]
            city_care_id = item["facility_id"]

    assert st_jude_key is not None and city_care_key is not None

    print("\n--- Test 1: Unauthorized Access Blocked ---")
    res = client.get("/api/v1/hospitals")
    assert res.status_code == 401, f"Expected 401, got {res.status_code}"
    print("PASS: Request without API key blocked with 401 Unauthorized.")

    print("\n--- Test 2: Authenticated Facility View ---")
    headers_stjude = {"X-API-Key": st_jude_key}
    res = client.get(f"/api/v1/hospitals/{st_jude_id}", headers=headers_stjude)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert res.json()["facility_name"] == "St. Jude General Hospital"
    print("PASS: St. Jude API key successfully fetched St. Jude facility details.")

    print("\n--- Test 3: Access Control Enforced (403 Forbidden for Other Facility's ID) ---")
    forbidden_res = client.get(f"/api/v1/hospitals/{city_care_id}", headers=headers_stjude)
    assert forbidden_res.status_code == 403, f"Expected 403, got {forbidden_res.status_code}"
    assert "Forbidden" in forbidden_res.json()["detail"]
    print("PASS: St. Jude API Key blocked from viewing City Care record (403 Forbidden).")

    print("\n--- Test 4: Delegated Facility User Login (/api/auth/login) ---")
    login_res = client.post("/api/auth/login", json={"username": "stjude_admin", "password": "password123"})
    assert login_res.status_code == 200, f"Expected 200, got {login_res.status_code}"
    login_data = login_res.json()
    assert login_data["facility_name"] == "St. Jude General Hospital"
    assert login_data["role"] == "FACILITY_ADMIN"
    assert "access_token" in login_data
    print("PASS: Facility admin login succeeded and returned session JWT.")

    print("\nALL FACILITY AUTH & RESTRICTED ACCESS TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_all_tests()
