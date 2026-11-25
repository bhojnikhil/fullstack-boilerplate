import re
from time import perf_counter
from uuid import uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Environment
from app.core.errors import error_response, internal_error_response

log = structlog.get_logger()
REQUEST_ID = "X-Request-Id"
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,63}")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, env: Environment) -> None:
        self.app = app
        self.env = env

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = perf_counter()
        supplied = Headers(scope=scope).get(REQUEST_ID, "")
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else uuid4().hex
        context = structlog.contextvars.bind_contextvars(request_id=request_id)
        status = 500
        started = False

        async def send_with_headers(message: Message) -> None:
            nonlocal status, started
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers[REQUEST_ID] = request_id
                headers["X-Content-Type-Options"] = "nosniff"
                headers["Content-Security-Policy"] = "frame-ancestors 'none'"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "no-referrer"
                if self.env != "development":
                    headers["Strict-Transport-Security"] = "max-age=31536000"
                started = True
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            log.exception("request_failed")
            if started:
                raise RuntimeError("Response stream failed") from None
            await internal_error_response()(scope, receive, send_with_headers)
        finally:
            # Route templates exclude user-provided paths, parameters and query strings.
            route = scope.get("route")
            state = scope.get("state", {})
            fields = {
                "method": scope["method"],
                "path": getattr(route, "path", "<unmatched>"),
                "status": status,
                "duration_ms": round((perf_counter() - start) * 1000, 2),
            }
            if "user_id" in state:
                fields["user_id"] = state["user_id"]
            log.info("http_request", **fields)
            structlog.contextvars.reset_contextvars(**context)


class ErrorMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = False

        async def track_response(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track_response)
        except Exception:
            if started:
                raise
            log.exception("request_failed")
            await internal_error_response()(scope, receive, send)


class TrustedHostEnvelopeMiddleware:
    def __init__(self, app: ASGIApp, allowed_hosts: list[str]) -> None:
        self.app = app
        self.guard = TrustedHostMiddleware(self.accept_host, allowed_hosts, www_redirect=False)

    @staticmethod
    async def accept_host(scope: Scope, receive: Receive, send: Send) -> None:
        """The host check calls this no-op only when the request may proceed."""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path = scope["path"]
            root_path = scope.get("root_path", "")
            if path == root_path or path.startswith(f"{root_path}/"):
                path = path.removeprefix(root_path)
            if path in {"/health", "/ready"}:
                await self.app(scope, receive, send)
                return

        rejected = False

        async def intercept_rejection(message: Message) -> None:
            nonlocal rejected
            rejected = True

        await self.guard(scope, receive, intercept_rejection)
        if rejected:
            await error_response(400, "invalid_host", "Invalid host header")(scope, receive, send)
        else:
            await self.app(scope, receive, send)


class CORSEnvelopeMiddleware(CORSMiddleware):
    def preflight_response(self, request_headers: Headers) -> Response:
        response = super().preflight_response(request_headers)
        if response.status_code < 400:
            return response
        headers = {
            name: value
            for name, value in response.headers.items()
            if name not in {"content-length", "content-type"}
        }
        return error_response(400, "cors_disallowed", "CORS preflight rejected", headers=headers)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        too_large = error_response(413, "body_too_large", "Request body is too large")
        length = Headers(scope=scope).get("content-length", "")
        declared = length.lstrip("0")
        limit_text = str(self.limit)
        if (
            declared.isascii()
            and declared.isdecimal()
            and (
                len(declared) > len(limit_text)
                or (len(declared) == len(limit_text) and declared > limit_text)
            )
        ):
            await too_large(scope, receive, send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > self.limit:
                await too_large(scope, receive, send)
                return
            body.extend(chunk)
            if not message.get("more_body", False):
                break

        buffered: bytes | None = bytes(body)
        del body

        async def replay_body() -> Message:
            nonlocal buffered
            if buffered is None:
                return await receive()
            replay, buffered = buffered, None
            return {"type": "http.request", "body": replay, "more_body": False}

        await self.app(scope, replay_body, send)
