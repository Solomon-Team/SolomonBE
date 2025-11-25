from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from app.core.config import JWT_SECRET, JWT_ALGORITHM
import secrets
import re

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(p: str) -> str:
    return pwd_ctx.hash(p)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def create_jwt_token(data: dict, expires_minutes: int = 60) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_jwt_token(token: str) -> dict:
    """
    Decode and validate JWT token.
    Raises JWTError if token is invalid or expired.
    """
    try:
        # jose.jwt.decode automatically validates expiration when present
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError:
        raise

def generate_magic_token() -> str:
    """
    Generate a secure random token for magic link authentication.
    Returns 64 character URL-safe string.
    """
    return secrets.token_urlsafe(48)  # 48 bytes = 64 chars base64url

def generate_join_code(structure_id: str) -> str:
    """
    Generate a human-readable join code for a structure.
    Format: {STRUCT}{RANDOM} (max 16 chars)
    """
    random_part = secrets.token_urlsafe(6)[:6].upper()  # 6 char random
    struct_part = structure_id[:3].upper()  # First 3 chars of structure
    return f"{struct_part}-{random_part}"

def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets strength requirements.
    Returns (is_valid, error_message)

    Requirements:
    - At least 8 characters
    - At least 1 uppercase letter
    - At least 1 lowercase letter
    - At least 1 number
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r"[0-9]", password):
        return False, "Password must contain at least one number"

    return True, ""
