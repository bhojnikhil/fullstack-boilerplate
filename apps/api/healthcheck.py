"""Container healthcheck probe.

Used by the Dockerfile ``HEALTHCHECK``. It must only use the standard library:
the runtime image must not need build tools (uv, pip, ``requests``)
for the probe to work.

Exit code 0 means healthy (HTTP 2xx within the timeout); anything else is
unhealthy; redirects are not followed. Usage::

    python healthcheck.py [URL] [EXPECTED_STATUS]
    python healthcheck.py --heartbeat PATH MAX_AGE_SECONDS

``--heartbeat`` is the worker's probe: healthy if PATH was modified within MAX_AGE_SECONDS.
The worker touches it every 30 seconds from its scheduler loop (no database needed).

The URL defaults to ``$HEALTHCHECK_URL`` or ``http://127.0.0.1:8000/health``.
With ``EXPECTED_STATUS``, only that exact HTTP status counts as success.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000/health"
TIMEOUT_SECONDS = 2.0


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not follow redirects: the health endpoint itself must answer 2xx.

    Returning None makes urllib raise HTTPError for the 3xx response, so a
    redirect (e.g. to a login page that returns 200) is reported unhealthy.
    """

    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def check(url: str, timeout: float = TIMEOUT_SECONDS, *, expected_status: int | None = None) -> int:
    """Return 0 for a matching response, or 1 if it differs or the probe fails."""
    try:
        with _opener.open(url, timeout=timeout) as response:
            status: int = response.status
    except urllib.error.HTTPError as error:
        with error:
            status = error.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 1
    if expected_status is not None:
        return 0 if status == expected_status else 1
    return 0 if 200 <= status < 300 else 1


def check_heartbeat(path: str, max_age: float) -> int:
    try:
        age = time.time() - os.stat(path).st_mtime
    except OSError:
        return 1
    return 0 if age <= max_age else 1


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--heartbeat":
        if len(argv) != 4:
            return 2
        return check_heartbeat(argv[2], float(argv[3]))
    url = argv[1] if len(argv) > 1 else os.environ.get("HEALTHCHECK_URL", DEFAULT_URL)
    expected_status = int(argv[2]) if len(argv) > 2 else None
    return check(url, expected_status=expected_status)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
