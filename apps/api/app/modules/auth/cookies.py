"""Web token transport: an httpOnly refresh cookie plus CSRF protection.

Only ``POST /v1/auth/refresh`` reads the cookie (it is scoped to that path), so it
is the only cookie-authenticated endpoint. It requires an allowed ``Origin`` and a
double-submitted CSRF token: the ``X-CSRF-Token`` header must equal the CSRF
cookie, and both must equal the HMAC of the session ID (a signed double submit).
The browser app learns the CSRF token from the sign-in/refresh response body.
"""

import uuid

from fastapi import Request
from starlette.responses import Response

from app.core import API_PREFIX
from app.core.client import ClientInfo
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.core.security import constant_time_equals, keyed_digest

REFRESH_COOKIE = "refresh_token"
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "X-CSRF-Token"
REFRESH_PATH = f"{API_PREFIX}/auth/refresh"


def csrf_token_for(config: Settings, session_id: uuid.UUID) -> str:
    return keyed_digest(config, "csrf", str(session_id))


def set_session_cookies(
    response: Response, config: Settings, refresh_token: str, csrf_token: str, max_age: int
) -> None:
    for name, value in ((REFRESH_COOKIE, refresh_token), (CSRF_COOKIE, csrf_token)):
        response.set_cookie(
            name,
            value,
            max_age=max_age,
            path=REFRESH_PATH,
            secure=config.secure_cookies,
            httponly=True,
            samesite="strict",
        )


def cleared_cookie_headers(config: Settings) -> list[tuple[str, str]]:
    """``Set-Cookie`` headers that remove both session cookies."""
    response = Response()
    for name in (REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(
            name, path=REFRESH_PATH, secure=config.secure_cookies, httponly=True, samesite="strict"
        )
    return [
        (key.decode("latin-1"), value.decode("latin-1"))
        for key, value in response.raw_headers
        if key == b"set-cookie"
    ]


def clear_session_cookies(response: Response, config: Settings) -> None:
    for name, value in cleared_cookie_headers(config):
        response.headers.append(name, value)


def require_trusted_origin(client: ClientInfo, config: Settings) -> None:
    """Reject cookie-setting or cookie-authenticated requests from other sites.

    Cookies are left alone on failure, so another site cannot sign the user out.
    """
    if client.origin is None or client.origin.lower() not in config.cors_origins:
        raise DomainError(ErrorCode.CSRF_FAILED)


def verify_csrf(request: Request, config: Settings, session_id: uuid.UUID) -> None:
    header = request.headers.get(CSRF_HEADER, "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    expected = csrf_token_for(config, session_id)
    if not (
        header
        and cookie
        and constant_time_equals(header, cookie)
        and constant_time_equals(header, expected)
    ):
        raise DomainError(ErrorCode.CSRF_FAILED)
