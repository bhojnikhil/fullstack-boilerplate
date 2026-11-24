"""Regression tests for the container healthcheck (defect #9).

The old Dockerfile probe was ``python -c "import requests; requests.get(...)"``:
it relied on ``requests`` leaking into the runtime image via Poetry, treated any
HTTP response (including 500) as healthy, and had no timeout.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType

import pytest

API_DIR = Path(__file__).resolve().parents[1]
SCRIPT = API_DIR / "healthcheck.py"
DOCKERFILE = API_DIR / "Dockerfile"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("healthcheck", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


healthcheck = _load_module()


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - name required by BaseHTTPRequestHandler
        if self.path == "/slow":
            time.sleep(1.0)
            status = 200
        elif self.path.startswith("/redirect/"):
            # e.g. /redirect/302 -> 302 to /200 (a healthy-looking page)
            self.send_response(int(self.path.rsplit("/", 1)[1]))
            self.send_header("Location", "/200")
            self.end_headers()
            return
        else:
            status = int(self.path.strip("/") or "200")
        self.send_response(status)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, format: str, *args: object) -> None:  # silence test output
        pass


@pytest.fixture(scope="module")
def server_url() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("status", [200, 204])
def test_healthy_on_2xx(server_url: str, status: int) -> None:
    assert healthcheck.check(f"{server_url}/{status}") == 0


@pytest.mark.parametrize("status", [404, 500, 503])
def test_unhealthy_on_error_status(server_url: str, status: int) -> None:
    assert healthcheck.check(f"{server_url}/{status}") == 1


@pytest.mark.parametrize("status", [301, 302, 307])
def test_unhealthy_on_redirect_to_healthy_page(server_url: str, status: int) -> None:
    """The endpoint itself must answer 2xx; a redirect (e.g. to a login page) is not healthy."""
    assert healthcheck.check(f"{server_url}/redirect/{status}") == 1


def test_unhealthy_when_nothing_listens() -> None:
    assert healthcheck.check("http://127.0.0.1:9/health", timeout=0.5) == 1


def test_unhealthy_on_timeout(server_url: str) -> None:
    assert healthcheck.check(f"{server_url}/slow", timeout=0.2) == 1


@pytest.mark.parametrize(
    ("path", "exit_code"), [("503", 0), ("500", 1), ("200", 1), ("redirect/302", 1)]
)
def test_exact_readiness_status(server_url: str, path: str, exit_code: int) -> None:
    assert healthcheck.main([str(SCRIPT), f"{server_url}/{path}", "503"]) == exit_code


def test_exact_readiness_status_rejects_connection_failure() -> None:
    assert healthcheck.check("http://127.0.0.1:9/ready", timeout=0.5, expected_status=503) == 1


def test_script_runs_with_stdlib_only(server_url: str) -> None:
    """``-I -S`` disables site-packages: the probe must not need third-party code."""
    ok = subprocess.run([sys.executable, "-I", "-S", str(SCRIPT), f"{server_url}/200"])
    bad = subprocess.run([sys.executable, "-I", "-S", str(SCRIPT), f"{server_url}/500"])
    assert ok.returncode == 0
    assert bad.returncode == 1


def test_dockerfile_uses_stdlib_probe() -> None:
    dockerfile = DOCKERFILE.read_text()
    match = re.search(r"^HEALTHCHECK\b.*?\bCMD\b(?P<cmd>[^\n]*)", dockerfile, re.M | re.S)
    assert match, "Dockerfile must declare a HEALTHCHECK"
    cmd = match.group("cmd")
    assert "healthcheck.py" in cmd
    assert "requests" not in cmd
