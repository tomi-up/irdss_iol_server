import os, pyotp
import hashlib, secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import jwt
from passlib.context import CryptContext
from pydantic_settings import BaseSettings, SettingsConfigDict
from cryptography.fernet import Fernet



# CONFIGURATION & ENVIRONMENT VARIABLES
class Settings(BaseSettings):
    SECRET_KEY: str = os.getenv("SECRET_KEY", "default-fallback-insecure-key")
    SECRET_ENCRYPTION_KEY: str = os.getenv("SECRET_ENCRYPTION_KEY", "")
    API_KEY: str = os.getenv("API_KEY", "irdss_api_key_default_2026")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Initialize the AES cipher suite using the key from your Settings
# (It will throw an error if you forget to put the key in your .env file, which is good for security!)
if not settings.SECRET_ENCRYPTION_KEY:
    raise ValueError("ERROR: SECRET_ENCRYPTION_KEY is missing from the .env file")
cipher_suite = Fernet(settings.SECRET_ENCRYPTION_KEY.encode('utf-8'))

# AUTHENTICATION & TOTP
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def generate_totp_secret() -> str:
    return pyotp.random_base32()

def verify_totp(secret: str, token: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(token)

# DATA PRIVACY ACT COMPLIANCE: AES ENCRYPTION
def aes_encrypt(data: str) -> str:
    """
    Encrypts sensitive string data (like patient names) using AES standard
    before it is saved to the PostgreSQL data lake.
    """
    if not data:
        return data
    encoded_data = data.encode('utf-8')
    encrypted_data = cipher_suite.encrypt(encoded_data)
    return encrypted_data.decode('utf-8')


def aes_decrypt(encrypted_data: str) -> str:
    """
    Decrypts AES encrypted data when the AI algorithms or the LGU interface
    need to securely read the health records.
    """
    if not encrypted_data:
        return encrypted_data
    encoded_data = encrypted_data.encode('utf-8')
    decrypted_data = cipher_suite.decrypt(encoded_data)
    return decrypted_data.decode('utf-8')




def hash_api_key(key: str) -> str:
    """
    Computes a SHA-256 hash of a raw API key for secure database storage & verification.
    """
    if not key:
        return ""
    return hashlib.sha256(key.encode('utf-8')).hexdigest()


# API KEY SECURITY DEPENDENCY
from fastapi import Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy.orm import Session
from app.database.db_connection import get_db

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

def verify_api_key(
    api_key: Optional[str] = Security(api_key_header),
    db: Session = Depends(get_db)
):
    """
    FastAPI dependency that hashes incoming X-API-Key header using SHA-256 and validates against active database keys.
    Returns the authenticated APIKey record containing the hospital's identity.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key. Header 'X-API-Key' is required."
        )

    # Compute SHA-256 hash of incoming raw API key
    incoming_hash = hash_api_key(api_key)

    # 1. Check database api_keys table against stored hash (or raw key fallback)
    from app.models.api_key import APIKey
    db_key = db.query(APIKey).filter(
        (APIKey.api_key == incoming_hash) | (APIKey.api_key == api_key),
        APIKey.is_active == True
    ).first()
    if db_key:
        return db_key

    # 2. Fallback to environment default API key (treated as system admin)
    if api_key == settings.API_KEY or incoming_hash == hash_api_key(settings.API_KEY):
        return APIKey(hospital_name="SYSTEM_ADMIN", api_key=incoming_hash, is_active=True)

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or inactive API Key. Access denied."
    )



def generate_irdss_api_key(hospital_name: str = "") -> tuple[str, str]:
    """
    Generates a secure raw API key prefixed with 'irdss_api_key_' along with its SHA-256 hash.
    Returns: (raw_key, hashed_key)
    """
    clean_name = "".join(c.lower() for c in hospital_name if c.isalnum())[:10]
    token = secrets.token_hex(8)
    if clean_name:
        raw_key = f"irdss_api_key_{clean_name}_{token}"
    else:
        raw_key = f"irdss_api_key_{token}"
    
    hashed_key = hash_api_key(raw_key)
    return raw_key, hashed_key



