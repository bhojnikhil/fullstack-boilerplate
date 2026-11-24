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
output=$(docker run --rm --env DATABASE_URL=postgresql://postgres:postgres@localhost/boilerplate \
    --env OPENSSL_armcap --entrypoint sh "$image" -ec \
    'test "$ENV" = production; exec timeout 10s uvicorn app.main:app --no-access-log' 2>&1) || status=$?
if [ "$status" -eq 0 ] || [ "$status" -eq 124 ] || [[ "$output" != *SECRET_KEY* ]]; then
    echo "Packaged API did not reject a missing SECRET_KEY (exit $status)" >&2
    exit 1
fi

echo "api: verified production HSTS, trusted hosts, JSON logs and missing-secret startup rejection"
