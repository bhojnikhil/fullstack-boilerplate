"""Credential primitives: access tokens, password hashing, opaque tokens and digests."""

import hashlib
import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.client import summarize_user_agent
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    InvalidAccessTokenError,
    constant_time_equals,
    create_access_token,
    decode_access_token,
    hash_password,
    keyed_digest,
    new_token,
    token_digest,
    verify_password,
)


def claims(config, **overrides):
    now = int(time.time())
    return {
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
        "sub": str(uuid4()),
        "sid": str(uuid4()),
        "iat": now,
        "exp": now + 900,
        "jti": "x",
        **overrides,
    }


def forge(config, key=None, algorithm="HS256", typ=ACCESS_TOKEN_TYPE, **overrides) -> str:
    payload = {k: v for k, v in claims(config, **overrides).items() if v is not None}
    return jwt.encode(payload, key or config.jwt_key, algorithm=algorithm, headers={"typ": typ})


def test_access_token_round_trip(config):
    user_id, session_id = uuid4(), uuid4()
    now = datetime.now(UTC)
    token, lifetime = create_access_token(user_id, session_id, config, now=now)
    decoded = decode_access_token(token, config)
    assert (decoded.user_id, decoded.session_id, lifetime) == (user_id, session_id, 900)
    assert decoded.issued_at == now.replace(microsecond=0)
    assert create_access_token(user_id, session_id, config, now=now)[0] != token  # jti


@pytest.mark.parametrize(
    "make",
    [
        lambda c: forge(c, typ="JWT"),
        lambda c: forge(c, aud="someone-else"),
        lambda c: forge(c, iss="someone-else"),
        lambda c: forge(c, exp=int(time.time()) - 31, iat=int(time.time()) - 931),
        lambda c: forge(c, iat=int(time.time()) + 3600),
        lambda c: forge(c, key="another-key-that-is-long-enough-for-hs256!"),
        lambda c: forge(c, algorithm="HS512", key=c.jwt_key * 2),  # Algorithm confusion.
        lambda c: forge(c, sid=None),
        lambda c: forge(c, jti=None),
        lambda c: forge(c, sub="not-a-uuid"),
        lambda c: forge(c, sid=12345),
        lambda c: jwt.encode(claims(c), key=None, algorithm="none"),
        lambda c: "a.b.c",
    ],
    ids=[
        "wrong-type",
        "wrong-audience",
        "wrong-issuer",
        "expired",
        "issued-in-future",
        "wrong-key",
        "other-algorithm",
        "no-session",
        "no-jti",
        "bad-subject",
        "bad-session",
        "unsigned",
        "malformed",
    ],
)
def test_invalid_access_tokens(config, make):
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(make(config), config)


async def test_password_hashing_and_rehash():
    hashed = await hash_password("correct horse battery staple")
    assert hashed.startswith("$argon2id$v=19$m=19456,t=2,p=1$")
    assert await verify_password("correct horse battery staple", hashed) == (True, None)
    assert await verify_password("wrong", hashed) == (False, None)

    weaker = Argon2Hasher(time_cost=1, memory_cost=8 * 1024, parallelism=1).hash("pw-123456789")
    valid, replacement = await verify_password("pw-123456789", weaker)
    assert valid
    assert replacement and replacement.startswith("$argon2id$v=19$m=19456,t=2,p=1$")


@pytest.mark.parametrize("stored", [None, "not-a-hash", "$2b$12$tooshort"])
async def test_missing_or_unknown_hashes_never_verify(stored):
    assert await verify_password("anything", stored) == (False, None)


def test_opaque_tokens_and_digests(config):
    first, second = new_token(), new_token()
    assert first != second and len(first) == 43
    assert token_digest(first) == hashlib.sha256(first.encode()).hexdigest()
    assert keyed_digest(config, "ip", "203.0.113.1") == keyed_digest(config, "ip", "203.0.113.1")
    assert keyed_digest(config, "ip", "203.0.113.1") != keyed_digest(config, "email", "203.0.113.1")
    other = config.model_copy(update={"secret_key": config.secret_key.__class__("y" * 64)})
    assert keyed_digest(config, "ip", "203.0.113.1") != keyed_digest(other, "ip", "203.0.113.1")
    assert constant_time_equals("abc", "abc") and not constant_time_equals("abc", "abd")


def test_derived_jwt_key_differs_from_the_signing_key(config):
    assert config.jwt_secret_key is None
    assert config.jwt_key != config.signing_key
    explicit = config.model_copy(update={"jwt_secret_key": config.secret_key})
    assert explicit.jwt_key == config.signing_key


@pytest.mark.parametrize(
    ("user_agent", "summary"),
    [
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.5 Safari/605.1.15",
            "Safari on macOS",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.0.0",
            "Edge on Windows",
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) CriOS/131.0.6778.73 Mobile/15E148 Safari/604.1",
            "Chrome on iOS",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
            "Firefox on Linux",
        ),
        ("okhttp/4.12.0", "Android app"),
        ("MyApp/1 CFNetwork/1568.200.51 Darwin/24.1.0", "iOS app on Apple OS"),
        ("something-else/1.0", "Unknown client"),
        ("", None),
        (None, None),
    ],
)
def test_user_agent_summary(user_agent, summary):
    assert summarize_user_agent(user_agent) == summary


def test_small_clock_differences_between_instances_are_tolerated(config):
    # Issued by an instance whose clock runs 10 seconds ahead.
    ahead = int(time.time()) + 10
    decode_access_token(forge(config, iat=ahead, exp=ahead + 900), config)
    # Just expired by the same amount.
    behind = int(time.time()) - 10
    decode_access_token(forge(config, iat=behind - 900, exp=behind), config)


def test_access_token_lifetime_is_configurable(config):
    short = config.model_copy(update={"access_token_expire_minutes": 5})
    token, lifetime = create_access_token(uuid4(), uuid4(), short)
    payload = jwt.decode(token, options={"verify_signature": False})
    assert lifetime == payload["exp"] - payload["iat"] == 300
    assert timedelta(seconds=lifetime) == timedelta(minutes=5)
