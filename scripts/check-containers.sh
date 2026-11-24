#!/usr/bin/env bash
# Assert that running Compose services are "as packaged": no mounts and a
# non-root effective UID. Used by CI (docker job) and `make smoke`.
#
# Usage: ./scripts/check-containers.sh SERVICE...
#   Honors the usual Compose env (COMPOSE_FILE, COMPOSE_PROJECT_NAME).
# Exit status: 0 only if every service passes every check.
# Regression test: scripts/test-check-containers.sh

set -uo pipefail

if [ $# -eq 0 ]; then
    echo "usage: $0 SERVICE..." >&2
    exit 2
fi

failures=0
fail() { echo "FAIL [$1]: $2" >&2; failures=$((failures + 1)); }

for svc in "$@"; do
    id=$(docker compose ps -q "$svc") || id=""
    if [ -z "$id" ]; then
        fail "$svc" "no running container"
        continue
    fi

    mounts=$(docker inspect --format '{{json .Mounts}}' "$id") || mounts="?"
    # Effective UID of the running process environment, not the configured
    # USER string: catches "root", "0", "0:0" and images without USER.
    uid=$(docker exec "$id" id -u) || uid=""
    echo "$svc: uid=${uid:-?} mounts=$mounts"

    if [ "$mounts" != "[]" ]; then
        fail "$svc" "has mounts (expected none): $mounts"
    fi
    if [ -z "$uid" ]; then
        fail "$svc" "could not determine the effective UID"
    elif [ "$uid" = "0" ]; then
        fail "$svc" "runs as root (uid 0)"
    fi
done

if [ "$failures" -gt 0 ]; then
    echo "$failures container check(s) failed" >&2
    exit 1
fi
echo "containers: all checks passed"
