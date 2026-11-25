"""
Security utilities for password hashing and JWT token generation.
No database access - pure utility functions.
"""

from datetime import UTC, datetime, timedelta

import bcrypt
from jose import jwt

from app.core.config import Settings


def hash_password(password: str) -> str:
    """
    Hash a plain text password using bcrypt.

    Note: Bcrypt has a 72 byte limit for passwords.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plain text password against a bcrypt hashed password.
    """
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(
    data: dict[str, str], config: Settings, expires_delta: timedelta | None = None
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Dictionary of claims to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token as string
    """
    to_encode: dict[str, str | datetime] = dict(data)
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=config.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(to_encode, config.signing_key, algorithm=config.jwt_algorithm)
    return encoded_jwt


def decode_access_token(token: str, config: Settings) -> dict[str, object]:
    """
    Decode and verify a JWT access token.

    Args:
        token: JWT token string

    Returns:
        Dictionary of claims from the token

    Raises:
        JWTError: If token is invalid or expired
    """
    payload: dict[str, object] = jwt.decode(
        token, config.signing_key, algorithms=[config.jwt_algorithm]
    )
    return payload
