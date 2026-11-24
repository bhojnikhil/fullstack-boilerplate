from collections.abc import Mapping
from enum import StrEnum
from http import HTTPStatus

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class ErrorCode(StrEnum):
    EMAIL_CONFLICT = "email_conflict"
    INVALID_CREDENTIALS = "invalid_credentials"
    INACTIVE_USER = "inactive_user"
    ITEM_NOT_FOUND = "item_not_found"
    ITEM_FORBIDDEN = "item_forbidden"
    OAUTH_UNAVAILABLE = "oauth_unavailable"
    OAUTH_FAILED = "oauth_failed"
    INVALID_CURSOR = "invalid_cursor"
    NOT_READY = "not_ready"
    INVALID_IDEMPOTENCY_KEY = "invalid_idempotency_key"
    IDEMPOTENCY_MISMATCH = "idempotency_mismatch"
    IDEMPOTENCY_IN_PROGRESS = "idempotency_in_progress"


class DomainError(Exception):
    def __init__(self, code: ErrorCode, message: str | None = None) -> None:
        self.code = code
        self.message = message
        super().__init__(code)


DOMAIN_ERRORS = {
    ErrorCode.EMAIL_CONFLICT: (409, "Email already registered"),
    ErrorCode.INVALID_CREDENTIALS: (401, "Incorrect email or password"),
    ErrorCode.INACTIVE_USER: (403, "Account is inactive"),
    ErrorCode.ITEM_NOT_FOUND: (404, "Item not found"),
    ErrorCode.ITEM_FORBIDDEN: (403, "Not authorized to access this item"),
    ErrorCode.OAUTH_UNAVAILABLE: (503, "Google sign-in is unavailable"),
    ErrorCode.OAUTH_FAILED: (400, "Google sign-in failed"),
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
    return error_response(status, exc.code, exc.message or default, headers=headers)


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


async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return error_response(500, "internal_error", "Internal server error")
