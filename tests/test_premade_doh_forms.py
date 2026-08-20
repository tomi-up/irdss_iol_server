import os
import sys
import time
import json
import base64
import hashlib

from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database.db_connection import SessionLocal
from app.models.hospitals import Facility
from app.models.assessment_models import FacilityAssessment, AssessmentAnswer

client = TestClient(app)

def test_premade_doh_assessment_forms():
    print("=== Testing Built-in Pre-made DOH Service Assessment Forms (Hospital, RHU, BHS) ===")

    # 1. Load RSA Private Key for Central HIS
    priv_key_path = r"c:\laragon\www\mock_hospitals\storage\keys\private_key.pem"
    assert os.path.exists(priv_key_path), "Private key PEM missing!"
    with open(priv_key_path, "r") as f:
        priv_pem = f.read()

    private_key = serialization.load_pem_private_key(priv_pem.encode('utf-8'), password=None)

    def create_signed_headers(method, path, body="", facility_code="FAC-000001", user_role="FACILITY_ADMIN"):
        timestamp = str(int(time.time()))
        nonce = f"nonce_{int(time.time()*1000000)}"
        system_code = "SYSTEM-001"
        key_id = "KEY-2026-001"
        body_sha256 = hashlib.sha256(body.encode('utf-8')).hexdigest()

        signing_str = f"{method}\n{path}\n{system_code}\n{key_id}\n{timestamp}\n{nonce}\n{body_sha256}"
        raw_sig = private_key.sign(
            signing_str.encode('utf-8'),
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        sig_b64 = base64.b64encode(raw_sig).decode('utf-8')

        return {
            "X-System-Code": system_code,
            "X-Key-ID": key_id,
            "X-Signature-Timestamp": timestamp,
            "X-Request-Nonce": nonce,
            "X-System-Signature": sig_b64,
            "X-User-ID": "stjude_admin",
            "X-User-Role": user_role,
            "X-Facility-Code": facility_code,
        }

    # Test 1: Hospital Form (FAC-000001)
    h_headers = create_signed_headers("GET", "/api/v1/assessments/form", facility_code="FAC-000001")
    res_h = client.get("/api/v1/assessments/form?facility_code=FAC-000001", headers=h_headers)
    assert res_h.status_code == 200, f"Hospital form failed: {res_h.text}"
    data_h = res_h.json()
    assert data_h["facility_type"] == "HOSPITAL"
    assert data_h["form"]["form_type"] == "HOSPITAL"
    print("PASS: Pre-made DOH Hospital Form loaded (Title:", data_h["form"]["title"], ")")

    # Test 2: RHU Form (FAC-000012 - Mintal RHU)
    rhu_headers = create_signed_headers("GET", "/api/v1/assessments/form", facility_code="FAC-000012")
    res_rhu = client.get("/api/v1/assessments/form?facility_code=FAC-000012", headers=rhu_headers)
    assert res_rhu.status_code == 200, f"RHU form failed: {res_rhu.text}"
    data_rhu = res_rhu.json()
    assert data_rhu["facility_type"] == "RHU"
    assert data_rhu["form"]["form_type"] == "RHU"
    sec_ids = [s["section_id"] for s in data_rhu["form"]["sections"]]
    assert "minor_surgery" in sec_ids and "supervisory_services" in sec_ids
    print("PASS: Pre-made DOH RHU Form loaded with Minor Surgery & Supervisory sections")

    # Test 3: BHS Form (FAC-000011 - Malagos BHS)
    bhs_headers = create_signed_headers("GET", "/api/v1/assessments/form", facility_code="FAC-000011")
    res_bhs = client.get("/api/v1/assessments/form?facility_code=FAC-000011", headers=bhs_headers)
    assert res_bhs.status_code == 200, f"BHS form failed: {res_bhs.text}"
    data_bhs = res_bhs.json()
    assert data_bhs["facility_type"] == "BHS"
    assert data_bhs["form"]["form_type"] == "BHS"
    print("PASS: Pre-made DOH BHS Form loaded with Basic Health Services")


    # Test 4: Submit Assessment for St. Jude Hospital via RSA Signed POST
    sub_payload = {
        "facility_id": 1,
        "assessment_type": "Monitoring",
        "assessment_date": "2026-08-11",
        "assessment_period": "CY 2026",
        "assessor_name": "Dr. Juan Dela Cruz",
        "general_remarks": "Fully compliant Level 1 Hospital facility.",
        "answers": [
            {"category": "medical_services", "item_code": "er", "item_label": "Emergency Room", "available": True, "operational": True, "remarks": "24/7 ER Bay"},
            {"category": "medical_services", "item_code": "icu", "item_label": "Intensive Care Unit", "available": True, "operational": True, "remarks": "6 Beds ICU"},
            {"category": "nursing_service", "item_code": "nursing_dept", "item_label": "Organized Nursing Department", "compliance": "COMPLIANT", "remarks": "Standard SOPs"},
            {"category": "personnel", "item_code": "num_physicians", "item_label": "Number of Physicians", "count": 18},
            {"category": "personnel", "item_code": "num_nurses", "item_label": "Number of Registered Nurses", "count": 42}
        ]
    }

    body_bytes = json.dumps(sub_payload, separators=(',', ':')).encode('utf-8')
    sub_headers = create_signed_headers("POST", "/api/v1/assessments/submit", body=body_bytes.decode('utf-8'), facility_code="FAC-000001")
    sub_headers["Content-Type"] = "application/json"

    res_sub = client.post("/api/v1/assessments/submit", content=body_bytes, headers=sub_headers)


    assert res_sub.status_code == 200, f"Submit failed: {res_sub.text}"
    sub_data = res_sub.json()
    assert sub_data["status"] == "success"
    print("PASS: DOH Service Assessment submitted to central PostgreSQL successfully (ID:", sub_data["assessment_id"], ")")

    print("\nALL PRE-MADE DOH SERVICE ASSESSMENT TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_premade_doh_assessment_forms()
