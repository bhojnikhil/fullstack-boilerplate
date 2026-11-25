"""Optional breached-password check against Have I Been Pwned (k-anonymity range API).

Only the first five hex characters of the password's SHA-1 leave the server, and
responses are padded so their size does not narrow the match. The check fails
open: if the service cannot be reached, the password is accepted and a warning
is logged. Enable it with ``PASSWORD_BREACH_CHECK=true``.
"""

import hashlib

import httpx
import structlog

RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
log = structlog.get_logger()


class BreachedPasswordChecker:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.transport = transport

    async def is_breached(self, password: str) -> bool:
        # SHA-1 is what the range API indexes; it is not used to store anything.
        digest = hashlib.sha1(password.encode(), usedforsecurity=False).hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(3, connect=2),
                transport=self.transport,
                headers={"Add-Padding": "true", "User-Agent": "boilerplate-api"},
            ) as client:
                response = await client.get(RANGE_URL.format(prefix=prefix))
                response.raise_for_status()
        except httpx.HTTPError:
            log.warning("password_breach_check_unavailable")
            return False
        for line in response.text.splitlines():
            candidate, _, count = line.partition(":")
            # Padding entries have a count of 0.
            if candidate.strip() == suffix and count.strip() not in {"", "0"}:
                return True
        return False
