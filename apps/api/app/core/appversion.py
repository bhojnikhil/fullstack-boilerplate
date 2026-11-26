"""Mobile version gate: ``GET /v1/meta`` and the 426 for clients below the minimum."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core import API_PREFIX
from app.core.client import PLATFORM_HEADER
from app.core.config import Settings, get_settings
from app.core.errors import ErrorCode, error_response

APP_VERSION_HEADER = "X-App-Version"
META_PATH = f"{API_PREFIX}/meta"
MOBILE_PLATFORMS = frozenset({"ios", "android"})
_CORE = re.compile(r"([0-9]{1,6})(?:\.([0-9]{1,6}))?(?:\.([0-9]{1,6}))?(?:[-+].*)?", re.ASCII)

Version = tuple[int, int, int]


def parse_version(value: str) -> Version | None:
    """The numeric major.minor.patch of "1.2.3" (a -suffix is ignored); None if invalid."""
    match = _CORE.fullmatch(value.strip())
    if match is None:
        return None
    major, minor, patch = (int(part or 0) for part in match.groups())
    return major, minor, patch


class AppVersionGate:
    """Rejects ios/android clients whose X-App-Version is below the configured minimum.

    The web app and clients that do not identify as mobile are never gated. A client that
    identifies as ios/android but sends no, or a malformed, ``X-App-Version`` is treated as
    below the minimum (builds that predate the header must update too). ``/v1/meta``, the
    health probes (outside ``/v1``) and CORS preflights stay reachable. With the default
    minimum ``0.0.0`` nobody is gated.
    """

    def __init__(self, app: ASGIApp, minimum: str) -> None:
        self.app = app
        self.minimum_text = minimum
        self.minimum = parse_version(minimum) or (0, 0, 0)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and self.minimum != (0, 0, 0) and self.blocked(scope):
            await error_response(
                426,
                ErrorCode.APP_UPDATE_REQUIRED,
                "Update the app to continue",
                details={"min_supported_app_version": self.minimum_text},
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)

    def blocked(self, scope: Scope) -> bool:
        path = scope["path"].removeprefix(scope.get("root_path", ""))
        if not path.startswith(f"{API_PREFIX}/") or path == META_PATH:
            return False
        if scope["method"] == "OPTIONS":
            return False
        headers = Headers(scope=scope)
        if headers.get(PLATFORM_HEADER, "").strip().lower() not in MOBILE_PLATFORMS:
            return False
        version = parse_version(headers.get(APP_VERSION_HEADER, ""))
        return version is None or version < self.minimum


class Meta(BaseModel):
    min_supported_app_version: str
    latest_app_version: str


router = APIRouter(tags=["meta"])


@router.get(META_PATH)
async def get(config: Annotated[Settings, Depends(get_settings)]) -> Meta:
    """Version information for clients; no authentication."""
    return Meta(
        min_supported_app_version=config.min_supported_app_version,
        latest_app_version=config.latest_app_version,
    )
