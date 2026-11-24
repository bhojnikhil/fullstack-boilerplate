"""Container healthcheck probe.

Used by the Dockerfile ``HEALTHCHECK``. It must only use the standard library:
the runtime image must not need build tools (uv, pip, ``requests``)
for the probe to work.

Exit code 0 means healthy (HTTP 2xx within the timeout); anything else is
unhealthy; redirects are not followed. Usage::

    python healthcheck.py [URL]

The URL defaults to ``$HEALTHCHECK_URL`` or ``http://127.0.0.1:8000/health``.
"""

from __future__ import annotations

import os
import sys
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


def check(url: str, timeout: float = TIMEOUT_SECONDS) -> int:
    """Return 0 if ``url`` itself answers 2xx within ``timeout``, else 1."""
    try:
        with _opener.open(url, timeout=timeout) as response:
            status: int = response.status
    except (urllib.error.URLError, TimeoutError, OSError):
        # HTTPError (3xx/4xx/5xx) is a subclass of URLError, so it lands here too.
        return 1
    return 0 if 200 <= status < 300 else 1


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else os.environ.get("HEALTHCHECK_URL", DEFAULT_URL)
    return check(url)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
