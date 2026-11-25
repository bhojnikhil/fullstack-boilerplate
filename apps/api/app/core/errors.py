from collections.abc import Mapping, Sequence
from enum import StrEnum
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class ErrorCode(StrEnum):
    # Authentication. Sign-in failures share one code so they cannot reveal accounts.
    INVALID_CREDENTIALS = "invalid_credentials"
    INVALID_TOKEN = "invalid_token"
    INVALID_REFRESH_TOKEN = "invalid_refresh_token"
    INACTIVE_USER = "inactive_user"
    CSRF_FAILED = "csrf_failed"
    RATE_LIMITED = "rate_limited"
    INVALID_OR_EXPIRED_TOKEN = "invalid_or_expired_token"
    PASSWORD_BREACHED = "password_breached"
    PASSWORD_NOT_SET = "password_not_set"
    REAUTHENTICATION_REQUIRED = "reauthentication_required"
    REAUTHENTICATION_FAILED = "reauthentication_failed"
    EMAIL_VERIFICATION_REQUIRED = "email_verification_required"
    SESSION_NOT_FOUND = "session_not_found"
    EMAIL_IN_USE = "email_in_use"
    ACCOUNT_DELETION_BLOCKED = "account_deletion_blocked"
    # Google sign-in.
    GOOGLE_SIGN_IN_DISABLED = "google_sign_in_disabled"
    INVALID_GOOGLE_TOKEN = "invalid_google_token"
    GOOGLE_UNAVAILABLE = "google_unavailable"
    GOOGLE_EMAIL_UNVERIFIED = "google_email_unverified"
    GOOGLE_LINK_REQUIRED = "google_link_required"
    GOOGLE_ACCOUNT_IN_USE = "google_account_in_use"
    GOOGLE_ALREADY_LINKED = "google_already_linked"
    GOOGLE_NOT_LINKED = "google_not_linked"
    LAST_SIGN_IN_METHOD = "last_sign_in_method"
    # Items and platform.
    ITEM_NOT_FOUND = "item_not_found"
    ITEM_FORBIDDEN = "item_forbidden"
    INVALID_CURSOR = "invalid_cursor"
    NOT_READY = "not_ready"
    INVALID_IDEMPOTENCY_KEY = "invalid_idempotency_key"
    IDEMPOTENCY_MISMATCH = "idempotency_mismatch"
    IDEMPOTENCY_IN_PROGRESS = "idempotency_in_progress"


class DomainError(Exception):
    """An expected failure, mapped to an HTTP status in one place (``DOMAIN_ERRORS``).

    ``commit=True`` commits the request's unit of work before the error response is
    sent. Use it only when the service wrote exactly the side effects that must
    survive the failure (for example an audit event or a revoked session).
    ``headers`` are extra raw response headers; repeated names (``Set-Cookie``) are kept.
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str | None = None,
        *,
        details: Mapping[str, object] | None = None,
        headers: Sequence[tuple[str, str]] = (),
        commit: bool = False,
    ) -> None:
        self.code = code
        self.message = message
        self.details = dict(details or {})
        self.headers = list(headers)
        self.commit = commit
        super().__init__(code)


class RateLimitedError(DomainError):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, retry_after)
        super().__init__(
            ErrorCode.RATE_LIMITED,
            details={"retry_after": self.retry_after},
            headers=[("Retry-After", str(self.retry_after))],
        )


DOMAIN_ERRORS = {
    ErrorCode.INVALID_CREDENTIALS: (
        401,
        "Incorrect email or password. New accounts can sign in after confirming their email.",
    ),
    ErrorCode.INVALID_TOKEN: (401, "Could not validate credentials"),
    ErrorCode.INVALID_REFRESH_TOKEN: (401, "Session expired. Sign in again."),
    ErrorCode.INACTIVE_USER: (403, "Account is inactive"),
    ErrorCode.CSRF_FAILED: (403, "Request failed CSRF validation"),
    ErrorCode.RATE_LIMITED: (429, "Too many requests. Try again later."),
    ErrorCode.INVALID_OR_EXPIRED_TOKEN: (400, "This link is invalid or has expired"),
    ErrorCode.PASSWORD_BREACHED: (
        422,
        "This password has appeared in a data breach. Choose a different password.",
    ),
    ErrorCode.PASSWORD_NOT_SET: (409, "This account has no password. Reset it to set one."),
    ErrorCode.REAUTHENTICATION_REQUIRED: (403, "Sign in again to continue"),
    ErrorCode.REAUTHENTICATION_FAILED: (403, "Could not confirm your identity"),
    ErrorCode.EMAIL_VERIFICATION_REQUIRED: (403, "Confirm your email address first"),
    ErrorCode.SESSION_NOT_FOUND: (404, "Session not found"),
    ErrorCode.EMAIL_IN_USE: (409, "This email address is already in use"),
    ErrorCode.ACCOUNT_DELETION_BLOCKED: (409, "The account cannot be deleted yet"),
    ErrorCode.GOOGLE_SIGN_IN_DISABLED: (404, "Google sign-in is not enabled"),
    ErrorCode.INVALID_GOOGLE_TOKEN: (401, "Google sign-in failed"),
    ErrorCode.GOOGLE_UNAVAILABLE: (503, "Google sign-in is temporarily unavailable"),
    ErrorCode.GOOGLE_EMAIL_UNVERIFIED: (
        403,
        "Google cannot confirm this email address. Sign up with your email, then link Google.",
    ),
    ErrorCode.GOOGLE_LINK_REQUIRED: (
        409,
        "An account already uses this email. Sign in to it, then link Google in settings.",
    ),
    ErrorCode.GOOGLE_ACCOUNT_IN_USE: (409, "This Google account is linked to another user"),
    ErrorCode.GOOGLE_ALREADY_LINKED: (409, "A different Google account is already linked"),
    ErrorCode.GOOGLE_NOT_LINKED: (404, "No Google account is linked"),
    ErrorCode.LAST_SIGN_IN_METHOD: (409, "Add another sign-in method before removing this one"),
    ErrorCode.ITEM_NOT_FOUND: (404, "Item not found"),
    ErrorCode.ITEM_FORBIDDEN: (403, "Not authorized to access this item"),
    ErrorCode.INVALID_CURSOR: (422, "Invalid pagination cursor"),
    ErrorCode.NOT_READY: (503, "Service is not ready"),
    ErrorCode.INVALID_IDEMPOTENCY_KEY: (422, "Invalid idempotency key"),
    ErrorCode.IDEMPOTENCY_MISMATCH: (422, "Idempotency key was used for a different request"),
    ErrorCode.IDEMPOTENCY_IN_PROGRESS: (409, "A request with this idempotency key is in progress"),
}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, object]


class ErrorEnvelope(BaseModel):
    error: ErrorBody


def error_response(
    status: int,
    code: str,
    message: str,
    *,
    details: dict[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "details": details or {}}},
        status_code=status,
        headers=headers,
    )


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    status, default = DOMAIN_ERRORS[exc.code]
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    response = error_response(
        status, exc.code, exc.message or default, details=exc.details, headers=headers
    )
    for name, value in exc.headers:
        response.headers.append(name, value)
    return response


async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
    status = HTTPStatus(exc.status_code) if exc.status_code in HTTPStatus else None
    code = status.name.lower() if status else "http_error"
    message = status.phrase if status else "Request failed"
    if exc.status_code < 500 and isinstance(exc.detail, str):
        message = exc.detail
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's input, context, and message can include credentials or other submitted values.
    fields = [{"location": error["loc"], "type": error["type"]} for error in exc.errors()]
    return error_response(
        422, "validation_error", "Request validation failed", details={"fields": fields}
    )


def internal_error_response() -> JSONResponse:
    return error_response(500, "internal_error", "Internal server error")
