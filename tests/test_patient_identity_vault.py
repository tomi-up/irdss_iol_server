import os
import tempfile
import unittest
from pathlib import Path

from cryptography.fernet import Fernet

from app.services.patient_identity_vault import (
    PatientIdentityVaultError,
    delete_patient_identity,
    load_patient_identity,
    store_patient_identity,
)


class PatientIdentityVaultTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        os.environ["IDENTITY_VAULT_DIR"] = self.tempdir.name
        os.environ["IDENTITY_VAULT_KEY"] = Fernet.generate_key().decode("ascii")

    def tearDown(self):
        os.environ.pop("IDENTITY_VAULT_DIR", None)
        os.environ.pop("IDENTITY_VAULT_KEY", None)
        self.tempdir.cleanup()

    def test_round_trip_and_acknowledged_delete(self):
        identity = {"full_name": "Test Patient", "phone": "09171234567"}
        store_patient_identity("ref_test123", identity)
        raw = (Path(self.tempdir.name) / "ref_test123.identity").read_bytes()
        self.assertNotIn(b"Test Patient", raw)
        self.assertEqual(load_patient_identity("ref_test123"), identity)
        self.assertTrue(delete_patient_identity("ref_test123"))
        self.assertIsNone(load_patient_identity("ref_test123"))

    def test_tampering_is_rejected(self):
        store_patient_identity("ref_tamper", {"full_name": "Test Patient"})
        path = Path(self.tempdir.name) / "ref_tamper.identity"
        raw = bytearray(path.read_bytes())
        raw[-1] ^= 1
        path.write_bytes(raw)
        with self.assertRaises(PatientIdentityVaultError):
            load_patient_identity("ref_tamper")


if __name__ == "__main__":
    unittest.main()

