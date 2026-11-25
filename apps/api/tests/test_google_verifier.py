"""GoogleIdTokenVerifier against tokens signed with local RSA keys (no network)."""

import json
import time
from datetime import UTC, datetime

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from google.auth import crypt
from google.auth import jwt as google_jwt

from app.integrations import google_id_token
from app.integrations.google_id_token import (
    CERTS_URL,
    GoogleIdTokenVerifier,
    GoogleTokenError,
    GoogleUnavailableError,
)

WEB_CLIENT = "web.apps.googleusercontent.com"
ANDROID_CLIENT = "android.apps.googleusercontent.com"


def new_key() -> tuple[bytes, bytes]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, public


KEY_A = new_key()
KEY_B = new_key()


def sign(private: bytes = KEY_A[0], kid: str = "key-a", **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://accounts.google.com",
        "aud": WEB_CLIENT,
        "sub": "1234567890",
        "email": "Person@Gmail.com",
        "email_verified": True,
        "name": "Person",
        "picture": "https://example.com/p.png",
        "iat": now,
        "exp": now + 3600,
        **overrides,
    }
    claims = {key: value for key, value in claims.items() if value is not None}
    signer = crypt.RSASigner.from_string(private, key_id=kid)
    return google_jwt.encode(signer, claims).decode()


class CertsServer:
    def __init__(self, certs: dict[str, bytes], max_age: int | None = 3600) -> None:
        self.certs = certs
        self.max_age = max_age
        self.requests: list[httpx.Request] = []
        self.fail = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert str(request.url) == CERTS_URL
        if self.fail:
            raise httpx.ConnectTimeout("down", request=request)
        headers = {"Cache-Control": f"public, max-age={self.max_age}"} if self.max_age else {}
        body = json.dumps({kid: pem.decode() for kid, pem in self.certs.items()})
        return httpx.Response(200, text=body, headers=headers)


def verifier(server: CertsServer) -> GoogleIdTokenVerifier:
    return GoogleIdTokenVerifier(
        [WEB_CLIENT, ANDROID_CLIENT], transport=httpx.MockTransport(server)
    )


async def test_valid_token():
    identity = await verifier(CertsServer({"key-a": KEY_A[1]})).verify(sign())
    assert identity.subject == "1234567890"
    assert identity.email == "person@gmail.com"
    assert identity.email_verified is True
    assert identity.name == "Person"
    assert identity.picture == "https://example.com/p.png"
    assert abs((datetime.now(UTC) - identity.issued_at).total_seconds()) < 5


@pytest.mark.parametrize(
    ("claims", "verified"),
    [
        ({"aud": ANDROID_CLIENT}, True),
        ({"iss": "accounts.google.com"}, True),
        ({"email_verified": "true"}, True),
        ({"email_verified": False}, False),
        ({"email_verified": None}, False),
    ],
)
async def test_accepted_variants(claims, verified):
    identity = await verifier(CertsServer({"key-a": KEY_A[1]})).verify(sign(**claims))
    assert identity.email_verified is verified


@pytest.mark.parametrize(
    "token",
    [
        sign(aud="other.apps.googleusercontent.com"),
        sign(iss="https://evil.example"),
        sign(exp=int(time.time()) - 60, iat=int(time.time()) - 3660),
        sign(iat=int(time.time()) + 600),
        sign(private=KEY_B[0]),  # Right key ID, wrong key.
        sign(email=None),
        sign(sub=None),
        sign(email="not-an-email"),
        "not.a.jwt",
        "x" * 40,
    ],
    ids=[
        "wrong-audience",
        "wrong-issuer",
        "expired",
        "issued-in-future",
        "bad-signature",
        "no-email",
        "no-subject",
        "malformed-email",
        "malformed",
        "garbage",
    ],
)
async def test_rejected_tokens(token):
    with pytest.raises(GoogleTokenError):
        await verifier(CertsServer({"key-a": KEY_A[1]})).verify(token)


async def test_certificates_are_cached_for_max_age(monkeypatch):
    server = CertsServer({"key-a": KEY_A[1]}, max_age=600)
    instance = verifier(server)
    clock = [1000.0]
    monkeypatch.setattr(google_id_token.time, "monotonic", lambda: clock[0])
    await instance.verify(sign())
    await instance.verify(sign())
    assert len(server.requests) == 1
    clock[0] += 601
    await instance.verify(sign())
    assert len(server.requests) == 2


async def test_unknown_key_id_refreshes_once_per_interval(monkeypatch):
    server = CertsServer({"key-a": KEY_A[1]})
    instance = verifier(server)
    clock = [1000.0]
    monkeypatch.setattr(google_id_token.time, "monotonic", lambda: clock[0])
    await instance.verify(sign())

    # Google rotated keys: the new key ID triggers an early refresh.
    server.certs = {"key-a": KEY_A[1], "key-b": KEY_B[1]}
    identity = await instance.verify(sign(private=KEY_B[0], kid="key-b"))
    assert identity.subject == "1234567890"
    assert len(server.requests) == 2

    # Garbage key IDs cannot force a refetch on every request.
    for _ in range(3):
        with pytest.raises(GoogleTokenError):
            await instance.verify(sign(kid="unknown"))
    assert len(server.requests) == 2
    clock[0] += 61
    with pytest.raises(GoogleTokenError):
        await instance.verify(sign(kid="unknown"))
    assert len(server.requests) == 3


async def test_outage_without_cached_certificates():
    server = CertsServer({"key-a": KEY_A[1]})
    server.fail = True
    with pytest.raises(GoogleUnavailableError):
        await verifier(server).verify(sign())


async def test_outage_keeps_using_the_last_good_certificates(monkeypatch):
    server = CertsServer({"key-a": KEY_A[1]}, max_age=None)
    instance = verifier(server)
    clock = [1000.0]
    monkeypatch.setattr(google_id_token.time, "monotonic", lambda: clock[0])
    await instance.verify(sign())
    clock[0] += 3601  # Default max-age elapsed.
    server.fail = True
    assert (await instance.verify(sign())).subject == "1234567890"
    assert len(server.requests) == 2


@pytest.mark.parametrize("body", ["[]", "{}", "not json"])
async def test_unexpected_certificate_documents(body):
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body))
    with pytest.raises(GoogleUnavailableError):
        await GoogleIdTokenVerifier([WEB_CLIENT], transport=transport).verify(sign())


async def test_certificate_fetch_errors_are_unavailable():
    transport = httpx.MockTransport(lambda request: httpx.Response(500))
    with pytest.raises(GoogleUnavailableError):
        await GoogleIdTokenVerifier([WEB_CLIENT], transport=transport).verify(sign())


def test_cached_transport_only_serves_the_certificate_url():
    from google.auth.exceptions import TransportError

    request = google_id_token._CachedCertsRequest(b"{}")
    response = request(CERTS_URL)
    assert (response.status, response.headers, response.data) == (200, {}, b"{}")
    with pytest.raises(TransportError):
        request("https://example.com/other")


@pytest.mark.parametrize(
    "claims",
    [
        {"sub": "1", "email": "a@example.com"},  # No issue time.
        {"sub": "1", "email": "a@example.com", "iat": "1700000000"},
        {"sub": "", "email": "a@example.com", "iat": 1700000000},
    ],
)
def test_incomplete_claims_are_rejected(claims):
    with pytest.raises(GoogleTokenError):
        google_id_token.identity_from_claims(claims)
