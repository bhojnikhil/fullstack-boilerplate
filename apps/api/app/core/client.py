"""What the API records about the calling client: no raw IPs or user-agent strings."""

from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.security import keyed_digest

Platform = Literal["web", "ios", "android", "other"]
PLATFORM_HEADER = "X-Platform"
PLATFORMS: frozenset[Platform] = frozenset({"web", "ios", "android"})

# Checked in order; the first match wins (Edge and Opera also claim to be Chrome, etc.).
_BROWSERS = (
    ("Edg/", "Edge"),
    ("OPR/", "Opera"),
    ("SamsungBrowser/", "Samsung Internet"),
    ("FxiOS/", "Firefox"),
    ("Firefox/", "Firefox"),
    ("CriOS/", "Chrome"),
    ("Chrome/", "Chrome"),
    ("Safari/", "Safari"),
    ("okhttp/", "Android app"),
    ("CFNetwork/", "iOS app"),
    ("Expo/", "Expo app"),
    ("python-httpx/", "httpx"),
    ("curl/", "curl"),
)
_SYSTEMS = (
    ("iPhone", "iOS"),
    ("iPad", "iPadOS"),
    ("Android", "Android"),
    ("CrOS", "ChromeOS"),
    ("Windows", "Windows"),
    ("Macintosh", "macOS"),
    ("Darwin/", "Apple OS"),
    ("Linux", "Linux"),
)


def summarize_user_agent(user_agent: str | None) -> str | None:
    """A coarse "Browser on OS" label for session lists, e.g. "Chrome on macOS"."""
    if not user_agent:
        return None
    sample = user_agent[:512]
    browser = next((name for marker, name in _BROWSERS if marker in sample), None)
    system = next((name for marker, name in _SYSTEMS if marker in sample), None)
    if browser and system:
        return f"{browser} on {system}"
    return browser or system or "Unknown client"


@dataclass(frozen=True)
class ClientInfo:
    ip_hash: str | None
    user_agent: str | None
    platform: Platform
    origin: str | None
    # Rate-limit identifier: the address itself is only kept in memory.
    ip: str

    @property
    def is_web(self) -> bool:
        return self.platform == "web"


def get_client_info(
    request: Request, config: Annotated[Settings, Depends(get_settings)]
) -> ClientInfo:
    # Behind a reverse proxy, run uvicorn with --forwarded-allow-ips so this is the client.
    ip = request.client.host if request.client else ""
    supplied = request.headers.get(PLATFORM_HEADER, "").strip().lower()
    platform: Platform = "other"
    for known in PLATFORMS:
        if supplied == known:
            platform = known
    return ClientInfo(
        ip_hash=keyed_digest(config, "ip", ip) if ip else None,
        user_agent=summarize_user_agent(request.headers.get("user-agent")),
        platform=platform,
        origin=request.headers.get("origin"),
        ip=ip or "unknown",
    )


Client = Annotated[ClientInfo, Depends(get_client_info)]
