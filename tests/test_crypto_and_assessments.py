import os
import sys
import time
import base64
import hashlib
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.database.db_connection import Base, get_db
from app.database.seed_hospitals import seed_hospitals_and_keys
from app.database.seed_system_credentials import seed_system_credentials
from app.database.init_crypto_and_templates import init_db_crypto_and_templates
from app.models.hospitals import Facility

client = TestClient(app)

def test_full_system_flow():
    print("=== Testing 12-Step Architecture: RSA Crypto, Replay Protection & 3-Layer Auth ===")
    
    # 1. Load registered system credential public key & private key
    priv_key_path = r"c:\laragon\www\mock_hospitals\storage\keys\private_key.pem"
    assert os.path.exists(priv_key_path), "Private key PEM missing!"
    
    with open(priv_key_path, "r") as f:
        priv_pem = f.read()

    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    private_key = serialization.load_pem_private_key(priv_pem.encode('utf-8'), password=None)

    # 2. Test Dynamic Assessment Template Loading
    method = "GET"
    path = "/api/v1/assessments/template"
    timestamp = str(int(time.time()))
    nonce = f"nonce_{int(time.time()*1000)}"
    system_code = "SYSTEM-001"
    key_id = "KEY-2026-001"
    facility_code = "FAC-000001"
    user_id = "stjude_admin"
    user_role = "FACILITY_ADMIN"

    body_sha256 = hashlib.sha256(b"").hexdigest()
    signing_str = f"{method}\n{path}\n{system_code}\n{key_id}\n{timestamp}\n{nonce}\n{body_sha256}"

    raw_sig = private_key.sign(
        signing_str.encode('utf-8'),
        padding.PKCS1v15(),
        hashes.SHA256()
    )
    sig_b64 = base64.b64encode(raw_sig).decode('utf-8')

    headers = {
        "X-System-Code": system_code,
        "X-Key-ID": key_id,
        "X-Signature-Timestamp": timestamp,
        "X-Request-Nonce": nonce,
        "X-System-Signature": sig_b64,
        "X-User-ID": user_id,
        "X-User-Role": user_role,
        "X-Facility-Code": facility_code,
    }

    res = client.get("/api/v1/assessments/template?facility_code=FAC-000001", headers=headers)
    print("Assessment Template Response Status:", res.status_code)
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    data = res.json()
    print("Loaded Assessment Template:", data["template_name"], f"({len(data['sections'])} sections)")

    # 3. Test Replay Protection (Re-sending exact same nonce)
    replay_res = client.get("/api/v1/assessments/template?facility_code=FAC-000001", headers=headers)
    print("Replay Attack Test Status:", replay_res.status_code)
    assert replay_res.status_code == 403, f"Expected 403 replay blocked, got {replay_res.status_code}"
    print("PASS: Replay attack with duplicated nonce blocked (403 Forbidden).")

    print("\nALL CRYPTO SIGNATURE & 3-LAYER AUTH TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_full_system_flow()
