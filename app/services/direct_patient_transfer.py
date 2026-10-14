"""Authorization only: patient packages travel between hospital backends."""
import base64
import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

ROOT = Path(__file__).resolve().parents[2] / "storage" / "patient_transfer"


def directory():
    path = Path(os.getenv("PATIENT_TRANSFER_DIRECTORY", str(ROOT / "facilities.json")))
    return json.loads(path.read_text(encoding="utf-8"))


def facility_entry(code):
    entry = directory().get(code)
    if not entry:
        raise ValueError("Hospital patient-transfer keys and endpoint are not configured.")
    endpoint = urlparse(entry["endpoint"])
    # HTTP is restricted to this prototype's loopback host. No user supplied URLs.
    if endpoint.scheme != "https" and not (
        endpoint.scheme == "http" and endpoint.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("Patient-transfer endpoint requires HTTPS.")
    if endpoint.username or endpoint.password or endpoint.fragment:
        raise ValueError("Invalid patient-transfer endpoint.")
    if len(base64.b64decode(entry["encryption_public_key"], validate=True)) != 32:
        raise ValueError("Invalid hospital payload public key.")
    return entry


def b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def issue_ticket(referral_id, transfer_id, source_code, recipient_code):
    source = facility_entry(source_code)
    recipient = facility_entry(recipient_code)
    now = int(time.time())
    claims = {
        "iss": "irdss-iol", "aud": "irdss-patient-transfer", "scope": "patient:read",
        "iat": now, "exp": now + 60, "jti": uuid.uuid4().hex,
        "referral_id": referral_id, "transfer_id": transfer_id,
        "source_code": source_code, "recipient_code": recipient_code,
        "source_local_id": source["local_facility_id"],
        "recipient_local_id": recipient["local_facility_id"],
        "recipient_public_key": recipient["encryption_public_key"],
    }
    unsigned = b64url(b'{"alg":"RS256","typ":"JWT"}') + "." + b64url(
        json.dumps(claims, separators=(",", ":")).encode("utf-8")
    )
    key = serialization.load_pem_private_key((ROOT / "authorization-private.pem").read_bytes(), password=None)
    signature = key.sign(unsigned.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return {
        "ticket": unsigned + "." + b64url(signature), "endpoint": source["endpoint"],
        "source_signing_public_key": source["signing_public_key"], "claims": claims,
    }


def verify_ticket(token):
    header, payload, signature = token.split(".")
    decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    if json.loads(decode(header)) != {"alg": "RS256", "typ": "JWT"}:
        raise ValueError("Unsupported transfer authorization.")
    key = serialization.load_pem_public_key((ROOT / "authorization-public.pem").read_bytes())
    key.verify(decode(signature), (header + "." + payload).encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    claims = json.loads(decode(payload))
    now = int(time.time())
    if (claims.get("iss") != "irdss-iol" or claims.get("aud") != "irdss-patient-transfer"
            or claims.get("scope") != "patient:read" or claims["exp"] <= now
            or claims["iat"] > now + 5 or claims["exp"] - claims["iat"] > 60):
        raise ValueError("Expired or invalid transfer authorization.")
    return claims
