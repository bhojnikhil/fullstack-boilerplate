#!/usr/bin/env bash
# Regression test for the Docker build-context ignore files:
#   - apps/api/.dockerignore             (context: apps/api)
#   - apps/web/Dockerfile.dockerignore   (context: repository root)
#
# For each, builds a temp context filled with dummy secrets/caches (at the app
# root and nested), asks Docker for the exact context it would send
# (FROM scratch + COPY, exported with --output type=local), and asserts what got
# in and what stayed out.
#
# Usage: ./scripts/test-dockerignore.sh   (requires Docker with BuildKit)

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

failures=0
fail() { echo "FAIL [$1]: $2" >&2; failures=$((failures + 1)); }

# Files that must never reach an image (app root and nested copies of each).
EXCLUDED=(
    .env .env.local .env.production
    key.pem dev.key cert.p12 upload.jks release.keystore
    google-services.json GoogleService-Info.plist
    test.db data.sqlite3
)
# Example env files must still be available to the build.
INCLUDED=(.env.example .env.local.example app.txt)

# check NAME IGNORE_FILE APP_DIR_IN_CONTEXT [PATHS_OUTSIDE_ALLOWLIST...]
check() {
    local name=$1 ignore=$2 app=$3
    shift 3
    local ctx="$WORK/ctx-$name" out="$WORK/out-$name"
    mkdir -p "$ctx/$app/nested/deeper"
    cp "$ROOT/$ignore" "$ctx/.dockerignore"
    for f in "${EXCLUDED[@]}" "${INCLUDED[@]}"; do
        for rel in "" nested/ nested/deeper/; do
            echo dummy > "$ctx/$app/$rel$f"
        done
    done
    for p in "$@"; do
        mkdir -p "$ctx/$(dirname "$p")"
        echo dummy > "$ctx/$p"
    done
    printf 'FROM scratch\nCOPY . /\n' > "$WORK/Dockerfile.$name"
    docker build -q -f "$WORK/Dockerfile.$name" --output "type=local,dest=$out" "$ctx" >/dev/null

    for rel in "" nested/ nested/deeper/; do
        for f in "${EXCLUDED[@]}"; do
            [ -e "$out/$app/$rel$f" ] && fail "$name" "$app/$rel$f was sent to the build context"
        done
        for f in "${INCLUDED[@]}"; do
            [ -e "$out/$app/$rel$f" ] || fail "$name" "$app/$rel$f was excluded but should be kept"
        done
    done
    for p in "$@"; do
        [ -e "$out/$p" ] && fail "$name" "$p (outside the allowlist) was sent to the build context"
    done
    return 0
}

# API: context is apps/api itself.
check api apps/api/.dockerignore .

# Web: context is the repo root; only the web app, shared config and workspace
# manifests may be sent.
check web apps/web/Dockerfile.dockerignore apps/web \
    apps/api/app/main.py docs/notes.md scripts/run.sh .env \
    apps/web/node_modules/pkg/index.js apps/web/.next/cache/x

if [ "$failures" -gt 0 ]; then
    echo "$failures dockerignore check(s) failed" >&2
    exit 1
fi
echo "dockerignore: all checks passed"
