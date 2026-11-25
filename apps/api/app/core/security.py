"""Credential primitives: password hashing, access tokens, opaque tokens and keyed hashes.

No database access. Services decide what to store and when.
"""

import hashlib
import hmac
import secrets
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import cache
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import HashVerificationError, UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.base import ensure_bytes
from pwdlib.hashers.bcrypt import BcryptHasher
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings

# Header type from RFC 9068 (JWT access tokens); JWTs of any other type are rejected.
ACCESS_TOKEN_TYPE = "at+jwt"
# Tolerated clock difference between API instances for iat/exp checks.
ACCESS_TOKEN_LEEWAY_SECONDS = 30
BCRYPT_MAX_BYTES = 72


class LegacyBcryptHasher(BcryptHasher):
    """Verifies hashes written before argon2id (bcrypt 4.x).

    bcrypt 4.x silently used only the first 72 bytes of a password, while bcrypt 5
    raises for longer input. Truncating here reproduces the original check, and a
    successful login replaces the hash with argon2id of the full password.
    """

    def verify(self, password: str | bytes, hash: str | bytes) -> bool:
        return super().verify(ensure_bytes(password)[:BCRYPT_MAX_BYTES], hash)


# OWASP Password Storage Cheat Sheet minimum for argon2id: 19 MiB, 2 iterations, 1 lane.
# Raising these values makes existing hashes "need rehash" on the next successful login.
ARGON2 = Argon2Hasher(time_cost=2, memory_cost=19 * 1024, parallelism=1)
PASSWORDS = PasswordHash((ARGON2, LegacyBcryptHasher()))
# Each argon2 computation allocates memory_cost; bound how many run at once.
_HASH_SLOTS = threading.BoundedSemaphore(4)


@cache
def _dummy_hash() -> str:
    return ARGON2.hash(secrets.token_urlsafe(16))


def _hash(password: str) -> str:
    with _HASH_SLOTS:
        return PASSWORDS.hash(password)


def _verify(password: str, hashed: str) -> tuple[bool, str | None]:
    with _HASH_SLOTS:
        try:
            return PASSWORDS.verify_and_update(password, hashed)
        except (UnknownHashError, HashVerificationError):
            return False, None


async def hash_password(password: str) -> str:
    return await run_in_threadpool(_hash, password)


async def verify_password(password: str, hashed: str | None) -> tuple[bool, str | None]:
    """Return (valid, replacement hash or None).

    Accounts without a password are checked against a dummy hash so the response
    time does not reveal whether an account (or a password) exists.
    """
    valid, updated = await run_in_threadpool(_verify, password, hashed or _dummy_hash())
    if hashed is None:
        return False, None
    return valid, updated


@dataclass(frozen=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    issued_at: datetime


class InvalidAccessTokenError(Exception):
    pass


def create_access_token(
    user_id: UUID, session_id: UUID, config: Settings, *, now: datetime | None = None
) -> tuple[str, int]:
    """Return a signed access token and its lifetime in seconds."""
    issued = int((now or datetime.now(UTC)).timestamp())
    lifetime = config.access_token_expire_minutes * 60
    payload = {
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
        "sub": str(user_id),
        "sid": str(session_id),
        "iat": issued,
        "exp": issued + lifetime,
        "jti": secrets.token_hex(16),
    }
    token = jwt.encode(
        payload, config.jwt_key, algorithm=config.jwt_algorithm, headers={"typ": ACCESS_TOKEN_TYPE}
    )
    return token, lifetime


def decode_access_token(token: str, config: Settings) -> AccessClaims:
    try:
        decoded = jwt.decode_complete(
            token,
            config.jwt_key,
            algorithms=[config.jwt_algorithm],
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
            options={"require": ["iss", "aud", "sub", "sid", "iat", "exp", "jti"]},
            leeway=ACCESS_TOKEN_LEEWAY_SECONDS,
        )
        if decoded["header"].get("typ") != ACCESS_TOKEN_TYPE:
            raise InvalidAccessTokenError
        payload = decoded["payload"]
        return AccessClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
        )
    except (jwt.PyJWTError, ValueError, TypeError, AttributeError) as err:
        raise InvalidAccessTokenError from err


def new_token() -> str:
    """An opaque, URL-safe token with 256 bits of entropy."""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """Storage form of an opaque token.

    Tokens are random, so an unkeyed SHA-256 is enough: a leaked table does not
    reveal usable tokens, and lookups by digest leak nothing useful through timing.
    """
    return hashlib.sha256(token.encode()).hexdigest()


def keyed_digest(config: Settings, purpose: str, value: str) -> str:
    """HMAC-SHA256 under a per-purpose key derived from SECRET_KEY.

    Used for values that are low-entropy or personal (IP addresses, emails) so
    the stored digest cannot be reversed by enumeration without the server key.
    """
    key = hmac.new(config.signing_key.encode(), f"purpose:{purpose}".encode(), hashlib.sha256)
    return hmac.new(key.digest(), value.encode(), hashlib.sha256).hexdigest()


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())
