"""Move legacy direct patient identity out of PostgreSQL into the encrypted vault.

This script is idempotent. It verifies every vault write before clearing the
legacy encrypted referral columns and commits all PostgreSQL updates together.
"""

from app.database.db_connection import SessionLocal
from app.models.referral_model import Referral
from app.services.patient_identity_vault import load_patient_identity, store_patient_identity
from app.utils.security import aes_decrypt


IDENTITY_COLUMNS = {
    "full_name": "patient_full_name",
    "date_of_birth": "patient_dob",
    "phone": "patient_phone",
    "address": "patient_address",
    "civil_status": "patient_civil_status",
    "philhealth_number": "patient_philhealth_number",
    "philhealth_status": "patient_philhealth_status",
    "consent_signer_name": "consent_signer_name",
    "consent_representative_relationship": "consent_representative_relationship",
}


def decrypt_legacy(value: str | None) -> str | None:
    if not value:
        return None
    return aes_decrypt(value)


def main() -> None:
    db = SessionLocal()
    migrated = 0
    try:
        referrals = db.query(Referral).filter(
            (Referral.patient_full_name.is_not(None))
            | (Referral.patient_dob.is_not(None))
            | (Referral.patient_phone.is_not(None))
            | (Referral.patient_address.is_not(None))
            | (Referral.patient_civil_status.is_not(None))
            | (Referral.patient_philhealth_number.is_not(None))
            | (Referral.patient_philhealth_status.is_not(None))
            | (Referral.consent_signer_name.is_not(None))
            | (Referral.consent_representative_relationship.is_not(None))
        ).all()

        for referral in referrals:
            existing = load_patient_identity(referral.referral_id) or {}
            identity = dict(existing)
            for key, column in IDENTITY_COLUMNS.items():
                value = getattr(referral, column)
                if value and not identity.get(key):
                    identity[key] = decrypt_legacy(value)

            store_patient_identity(referral.referral_id, identity)
            if load_patient_identity(referral.referral_id) != identity:
                raise RuntimeError(f"Vault verification failed for referral {referral.referral_id}.")

            for column in IDENTITY_COLUMNS.values():
                setattr(referral, column, None)
            migrated += 1

        db.commit()
        remaining = db.query(Referral).filter(
            (Referral.patient_full_name.is_not(None))
            | (Referral.patient_dob.is_not(None))
            | (Referral.patient_phone.is_not(None))
            | (Referral.patient_address.is_not(None))
            | (Referral.patient_civil_status.is_not(None))
            | (Referral.patient_philhealth_number.is_not(None))
            | (Referral.patient_philhealth_status.is_not(None))
            | (Referral.consent_signer_name.is_not(None))
            | (Referral.consent_representative_relationship.is_not(None))
        ).count()
        print(f"Migrated {migrated} referral identity record(s) out of PostgreSQL; {remaining} direct-identity row(s) remain.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
