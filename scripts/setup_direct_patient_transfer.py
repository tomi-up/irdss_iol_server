"""Provision this local mock deployment's public directory and authorization pair."""
import json
import subprocess
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import text

from app.database.db_connection import engine
from app.services.direct_patient_transfer import ROOT

MOCK = Path("C:/laragon/www/mock_hospitals")
PHP = Path("C:/laragon/bin/php/php-8.3.30-Win32-vs16-x64/php.exe")


def main():
    result = subprocess.run([str(PHP), str(MOCK / "scripts/setup_patient_transfer.php")],
                            capture_output=True, text=True, check=True)
    local_facilities = json.loads(result.stdout)
    ROOT.mkdir(parents=True, exist_ok=True)
    private_path = ROOT / "authorization-private.pem"
    public_path = ROOT / "authorization-public.pem"
    if not private_path.exists():
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        with private_path.open("xb") as handle:
            handle.write(key.private_bytes(serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        private_path.chmod(0o600)
    key = serialization.load_pem_private_key(private_path.read_bytes(), password=None)
    public_path.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,
                           serialization.PublicFormat.SubjectPublicKeyInfo))
    (MOCK / "storage/patient_transfer/iol-authorization-public.pem").write_bytes(public_path.read_bytes())
    with engine.connect() as connection:
        central = connection.execute(text("SELECT facility_code, facility_name FROM facilities")).mappings().all()
    central_names = {row["facility_name"].strip().casefold(): row["facility_code"] for row in central}
    path = ROOT / "facilities.json"
    entries = json.loads(path.read_text()) if path.exists() else {}
    count = 0
    for facility in local_facilities:
        code = central_names.get(facility["name"].strip().casefold())
        if code:
            entries[code] = facility
            count += 1
    path.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"Direct patient transfer configured for {count} matched mock hospitals. Private keys were not exported.")


if __name__ == "__main__":
    main()
