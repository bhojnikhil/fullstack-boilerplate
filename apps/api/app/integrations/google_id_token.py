"""Google ID-token verification (Sign in with Google on web, Android and iOS).

google-auth verifies the signature, issuer, audience and expiry. Google's signing
certificates are fetched with async httpx and cached per the response's
``Cache-Control: max-age``, so verification does no blocking I/O. This module never
requests or stores Google access or refresh tokens.
"""

import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import jwt
from google.auth import exceptions as google_exceptions
from google.auth import transport
from google.oauth2 import id_token
from structlog.contextvars import get_contextvars

from app.core.middleware import REQUEST_ID

CERTS_URL = "https://www.googleapis.com/oauth2/v1/certs"
DEFAULT_CERTS_MAX_AGE = 3600
MIN_FORCED_REFRESH_INTERVAL = 60
MAX_AGE_PATTERN = re.compile(r"max-age=(\d+)")


class GoogleTokenError(Exception):
    """The ID token is malformed, expired, for another audience or badly signed."""


class GoogleUnavailableError(Exception):
    """Google's signing certificates could not be fetched."""


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None
    issued_at: datetime


class _CertsResponse(transport.Response):
    def __init__(self, body: bytes) -> None:
        self._body = body

    @property
    def status(self) -> int:
        return 200

    @property
    def headers(self) -> Mapping[str, str]:
        return {}

    @property
    def data(self) -> bytes:
        return self._body


class _CachedCertsRequest(transport.Request):
    """A google-auth transport that serves the already-fetched certificates."""

    def __init__(self, certs: bytes) -> None:
        self.certs = certs

    def __call__(self, url: str, method: str = "GET", *args: Any, **kwargs: Any) -> _CertsResponse:
        if url != CERTS_URL or method != "GET":
            # google-auth's exception classes are not annotated.
            raise google_exceptions.TransportError("Unexpected request")  # type: ignore[no-untyped-call]
        return _CertsResponse(self.certs)


class GoogleIdTokenVerifier:
    def __init__(
        self,
        client_ids: Sequence[str],
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock_skew_seconds: int = 10,
    ) -> None:
        self.client_ids = list(client_ids)
        self.transport = transport
        self.clock_skew_seconds = clock_skew_seconds
        self._certs: bytes | None = None
        self._key_ids: frozenset[str] = frozenset()
        self._expires_at = 0.0
        self._forced_at = -float(MIN_FORCED_REFRESH_INTERVAL)

    async def verify(self, token: str) -> GoogleIdentity:
        try:
            key_id = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as err:
            raise GoogleTokenError from err
        certs = await self._fetch_certs()
        now = time.monotonic()
        if key_id not in self._key_ids and now - self._forced_at >= MIN_FORCED_REFRESH_INTERVAL:
            # Google rotates keys; refresh early, but not on every unknown key ID.
            self._forced_at = now
            certs = await self._fetch_certs(force=True)
        try:
            # verify_oauth2_token checks signature, issuer, audience and expiry (unannotated).
            claims = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
                token,
                _CachedCertsRequest(certs),
                audience=self.client_ids,
                clock_skew_in_seconds=self.clock_skew_seconds,
            )
        except (ValueError, google_exceptions.GoogleAuthError) as err:
            raise GoogleTokenError from err
        return identity_from_claims(claims)

    async def _fetch_certs(self, *, force: bool = False) -> bytes:
        if self._certs is not None and not force and time.monotonic() < self._expires_at:
            return self._certs
        request_id = get_contextvars().get("request_id")
        headers = {REQUEST_ID: request_id} if isinstance(request_id, str) else {}
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(5, connect=2), transport=self.transport, headers=headers
            ) as client:
                response = await client.get(CERTS_URL)
                response.raise_for_status()
            certs = json.loads(response.content)
            if not isinstance(certs, dict) or not certs:
                raise ValueError("Unexpected certificate document")
        except (httpx.HTTPError, ValueError) as err:
            if self._certs is not None:
                return self._certs  # Keep verifying with the last good keys.
            raise GoogleUnavailableError from err
        match = MAX_AGE_PATTERN.search(response.headers.get("cache-control", ""))
        max_age = int(match.group(1)) if match else DEFAULT_CERTS_MAX_AGE
        self._certs = response.content
        self._key_ids = frozenset(certs)
        self._expires_at = time.monotonic() + min(max(max_age, 60), 86_400)
        return self._certs


def identity_from_claims(claims: Mapping[str, Any]) -> GoogleIdentity:
    subject, email = claims.get("sub"), claims.get("email")
    issued_at = claims.get("iat")
    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(email, str)
        or "@" not in email
    ):
        raise GoogleTokenError
    if not isinstance(issued_at, int):
        raise GoogleTokenError
    name, picture = claims.get("name"), claims.get("picture")
    return GoogleIdentity(
        subject=subject,
        email=email.strip().lower(),
        # Google sends a JSON boolean; some older tokens used the string "true".
        email_verified=claims.get("email_verified") in (True, "true"),
        name=name[:255] if isinstance(name, str) and name.strip() else None,
        picture=picture if isinstance(picture, str) and len(picture) <= 500 else None,
        issued_at=datetime.fromtimestamp(issued_at, UTC),
    )
