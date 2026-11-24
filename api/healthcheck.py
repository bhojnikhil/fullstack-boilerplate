"""Container healthcheck probe.

Used by the Dockerfile ``HEALTHCHECK``. It must only use the standard library:
the runtime image must not need build tools (Poetry, pip extras, ``requests``)
for the probe to work.

Exit code 0 means healthy (HTTP 2xx within the timeout); anything else is
unhealthy. Usage::

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


def check(url: str, timeout: float = TIMEOUT_SECONDS) -> int:
    """Return 0 if ``url`` answers with a 2xx status within ``timeout``, else 1."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            status: int = response.status
    except (urllib.error.URLError, TimeoutError, OSError):
        # HTTPError (4xx/5xx) is a subclass of URLError, so it lands here too.
        return 1
    return 0 if 200 <= status < 300 else 1


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) > 1 else os.environ.get("HEALTHCHECK_URL", DEFAULT_URL)
    return check(url)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
