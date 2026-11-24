#!/usr/bin/env bash
# Regression test for api/.dockerignore and client/.dockerignore.
#
# For each build context, copies its .dockerignore into a temp context filled
# with dummy secrets/caches (at the root and nested), asks Docker for the exact
# build context it would send (FROM scratch + COPY, exported with
# --output type=local), and asserts what got in and what stayed out.
#
# Usage: ./scripts/test-dockerignore.sh   (requires Docker with BuildKit)

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

failures=0
fail() { echo "FAIL [$1]: $2" >&2; failures=$((failures + 1)); }

# Files that must never reach an image (root and nested copies of each).
EXCLUDED=(
    .env .env.local .env.production
    key.pem dev.key cert.p12 upload.jks release.keystore
    google-services.json GoogleService-Info.plist
    test.db data.sqlite3
)
# Example env files must still be available to the build.
INCLUDED=(.env.example .env.local.example app.txt)

for ctx in api client; do
    dir="$WORK/$ctx"
    mkdir -p "$dir/nested/deeper"
    cp "$ROOT/$ctx/.dockerignore" "$dir/.dockerignore"
    for f in "${EXCLUDED[@]}" "${INCLUDED[@]}"; do
        echo "dummy" > "$dir/$f"
        echo "dummy" > "$dir/nested/$f"
        echo "dummy" > "$dir/nested/deeper/$f"
    done
    printf 'FROM scratch\nCOPY . /\n' > "$WORK/Dockerfile.$ctx"

    out="$WORK/out-$ctx"
    docker build -q -f "$WORK/Dockerfile.$ctx" --output "type=local,dest=$out" "$dir" >/dev/null

    for rel in "" nested/ nested/deeper/; do
        for f in "${EXCLUDED[@]}"; do
            [ -e "$out/$rel$f" ] && fail "$ctx" "$rel$f was sent to the build context"
        done
        for f in "${INCLUDED[@]}"; do
            [ -e "$out/$rel$f" ] || fail "$ctx" "$rel$f was excluded but should be kept"
        done
    done
done

if [ "$failures" -gt 0 ]; then
    echo "$failures dockerignore check(s) failed" >&2
    exit 1
fi
echo ".dockerignore: all checks passed"
