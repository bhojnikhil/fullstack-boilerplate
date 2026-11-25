#!/usr/bin/env bash
# Verify the packaged API after `make smoke` starts and migrates the stack.
set -euo pipefail

# The loopback probe works with an allowlist containing only api.example.com.
# A normal API route on that same Host must still be rejected.
docker compose exec -T api python - <<'PY'
from urllib.error import HTTPError
from urllib.request import urlopen

with urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
try:
    urlopen("http://127.0.0.1:8000/v1", timeout=2)
except HTTPError as error:
    assert error.code == 400
else:
    raise AssertionError("Non-probe route accepted the loopback Host")
PY

# Sign-up to sign-in in production mode: the verification email goes over SMTP to
# Mailpit, and the web sign-in sets a Secure, httpOnly, SameSite=Strict refresh cookie.
docker compose exec -T api python - <<'PY'
import json
import os
import re
import time
import uuid
from urllib.parse import quote
from urllib.request import Request, urlopen

email = f"smoke-{uuid.uuid4().hex[:12]}@example.com"
password = "smoke-test-password-123"
origin = json.loads(os.environ["CORS_ORIGINS"])[0]


def call(path, body, headers=None):
    request = Request(
        f"http://127.0.0.1:8000{path}",
        method="POST",
        data=json.dumps(body).encode(),
        headers={"Host": "api.example.com", "Content-Type": "application/json", **(headers or {})},
    )
    with urlopen(request, timeout=5) as response:
        return response.status, response.headers, response.read()


assert call("/v1/auth/register", {"email": email, "password": password, "name": "Smoke"})[0] == 202
for _ in range(50):
    with urlopen(f"http://mailpit:8025/api/v1/search?query={quote('to:' + email)}", timeout=2) as r:
        messages = json.load(r)["messages"]
    if messages:
        break
    time.sleep(0.2)
else:
    raise AssertionError("The verification email did not reach Mailpit")
with urlopen(f"http://mailpit:8025/api/v1/message/{messages[0]['ID']}", timeout=2) as r:
    text = json.load(r)["Text"]
token = re.search(r"https://web\.example\.com/auth/verify-email#token=([\w-]+)", text).group(1)
assert call("/v1/auth/verify-email", {"token": token, "password": password})[0] == 204

status, headers, body = call(
    "/v1/auth/login",
    {"email": email, "password": password},
    {"X-Platform": "web", "Origin": origin},
)
assert status == 200 and json.loads(body)["user"]["email_verified"] is True
refresh = next(c for c in headers.get_all("Set-Cookie") if c.startswith("refresh_token="))
for attribute in ("httponly", "secure", "samesite=strict", "path=/v1/auth/refresh"):
    assert attribute in refresh.lower(), refresh
PY

docker compose logs --no-color --no-log-prefix api | docker compose exec -T api python -c '
import json
import sys

records = [json.loads(line) for line in sys.stdin if line.strip()]
assert any(record.get("event") == "http_request" and record.get("path") == "/health" for record in records)
assert any(record.get("logger") == "uvicorn.error" for record in records)
'

container=$(docker compose ps -q api)
image=$(docker inspect --format '{{.Image}}' "$container")
# Test the image outside Compose so the overlay cannot supply the production default.
# Bound startup time so a regression that boots without a key fails quickly.
status=0
run_args=(--rm --env DATABASE_URL=postgresql://postgres:postgres@localhost/boilerplate)
if [[ -n ${OPENSSL_armcap:-} ]]; then
    run_args+=(--env "OPENSSL_armcap=$OPENSSL_armcap")
fi
output=$(docker run "${run_args[@]}" --entrypoint sh "$image" -ec \
    'test "$ENV" = production; exec timeout 10s uvicorn app.main:app --no-access-log' 2>&1) || status=$?
if [ "$status" -eq 0 ] || [ "$status" -eq 124 ] || [[ "$output" != *SECRET_KEY* ]]; then
    echo "Packaged API did not reject a missing SECRET_KEY (exit $status)" >&2
    exit 1
fi

# Every other production setting present, but no access-token signing key.
status=0
run_args+=(--env "SECRET_KEY=$(openssl rand -hex 32)" --env EMAIL_BACKEND=smtp
    --env WEB_URL=https://web.example.com)
output=$(docker run "${run_args[@]}" --entrypoint sh "$image" -ec \
    'exec timeout 10s uvicorn app.main:app --no-access-log' 2>&1) || status=$?
if [ "$status" -eq 0 ] || [ "$status" -eq 124 ] || [[ "$output" != *JWT_SECRET_KEY* ]]; then
    echo "Packaged API did not reject a missing JWT_SECRET_KEY (exit $status)" >&2
    exit 1
fi

echo "api: verified production HSTS, trusted hosts, sign-up email over SMTP, secure refresh" \
    "cookie, JSON logs and missing-secret startup rejection"
