"""Encrypted, expiring patient-identity relay outside PostgreSQL.

The central workflow database stores referral/routing metadata only. Direct
identity is kept in a Fernet-authenticated ciphertext file until the selected
receiving facility confirms that it imported the patient locally.

This is a transitional secure relay. A later phase will encrypt the package to
the receiving facility's own public encryption key so Central IRDSS cannot
decrypt it.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


_SAFE_REFERRAL_ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_DEFAULT_TTL_HOURS = 168


class PatientIdentityVaultError(RuntimeError):
    pass


def _vault_root() -> Path:
    configured = os.getenv("IDENTITY_VAULT_DIR", "").strip()
    root = Path(configured) if configured else Path(__file__).resolve().parents[2] / "storage" / "patient_identity_vault"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _vault_path(referral_id: str) -> Path:
    if not _SAFE_REFERRAL_ID.fullmatch(referral_id):
        raise PatientIdentityVaultError("Invalid referral identifier for identity vault.")
    return _vault_root() / f"{referral_id}.identity"


def _cipher() -> Fernet:
    key = os.getenv("IDENTITY_VAULT_KEY", "").strip()
    if not key:
        raise PatientIdentityVaultError("IDENTITY_VAULT_KEY is not configured.")
    try:
        return Fernet(key.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise PatientIdentityVaultError("IDENTITY_VAULT_KEY is invalid.") from exc


def store_patient_identity(referral_id: str, identity: dict[str, Any], ttl_hours: int | None = None) -> None:
    ttl = ttl_hours if ttl_hours is not None else int(os.getenv("IDENTITY_VAULT_TTL_HOURS", _DEFAULT_TTL_HOURS))
    now = datetime.now(timezone.utc)
    envelope = {
        "version": 1,
        "referral_id": referral_id,
        "created_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=max(1, ttl))).isoformat(),
        "identity": identity,
    }
    ciphertext = _cipher().encrypt(json.dumps(envelope, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    destination = _vault_path(referral_id)
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(ciphertext)
    temporary.replace(destination)


def load_patient_identity(referral_id: str) -> dict[str, Any] | None:
    path = _vault_path(referral_id)
    if not path.exists():
        return None
    try:
        envelope = json.loads(_cipher().decrypt(path.read_bytes()).decode("utf-8"))
        expires_at = datetime.fromisoformat(envelope["expires_at"])
    except (InvalidToken, ValueError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise PatientIdentityVaultError("Patient identity package is invalid or cannot be decrypted.") from exc

    if expires_at <= datetime.now(timezone.utc):
        path.unlink(missing_ok=True)
        return None
    if envelope.get("referral_id") != referral_id or not isinstance(envelope.get("identity"), dict):
        raise PatientIdentityVaultError("Patient identity package does not match the referral.")
    return envelope["identity"]


def delete_patient_identity(referral_id: str) -> bool:
    path = _vault_path(referral_id)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed

