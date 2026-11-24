#!/usr/bin/env bash
# Regression test for scripts/check-containers.sh, using a fake `docker` on
# PATH (no Docker needed). Each case sets per-service state through env vars.
#
# Usage: ./scripts/test-check-containers.sh

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

# Fake docker: state comes from FAKE_<SVC>_{ID,UID,MOUNTS}.
cat > "$WORK/docker" <<'FAKE'
#!/usr/bin/env bash
var() { local v="FAKE_$1"; printf '%s' "${!v-}"; }
case "$1 $2" in
    "compose ps")   svc=$(echo "$4" | tr a-z A-Z); var "${svc}_ID"; echo ;;
    "inspect --format")
        svc=$(echo "${4%-id}" | tr a-z A-Z); var "${svc}_MOUNTS"; echo ;;
    exec*)
        svc=$(echo "${2%-id}" | tr a-z A-Z); u=$(var "${svc}_UID")
        [ -n "$u" ] || exit 1; echo "$u" ;;
esac
FAKE
chmod +x "$WORK/docker"

failures=0
# expect EXIT_CODE DESCRIPTION -- VAR=VALUE...
expect() {
    local want=$1 desc=$2; shift 3
    local got=0
    env PATH="$WORK:$PATH" \
        FAKE_API_ID=api-id FAKE_API_UID=10001 FAKE_API_MOUNTS='[]' \
        FAKE_WEB_ID=web-id FAKE_WEB_UID=1000 FAKE_WEB_MOUNTS='[]' \
        "$@" "$ROOT/scripts/check-containers.sh" api web >/dev/null 2>&1 || got=$?
    if [ "$got" -eq "$want" ]; then
        echo "ok   - $desc"
    else
        echo "FAIL - $desc (exit $got, want $want)"
        failures=$((failures + 1))
    fi
}

expect 0 "both non-root, no mounts"             --
expect 1 "api root, web non-root (first fails)" -- FAKE_API_UID=0
expect 1 "api non-root, web root (last fails)"  -- FAKE_WEB_UID=0
expect 1 "api has a bind mount"                 -- 'FAKE_API_MOUNTS=[{"Type":"bind"}]'
expect 1 "web has a bind mount"                 -- 'FAKE_WEB_MOUNTS=[{"Type":"bind"}]'
expect 1 "api container not running"            -- FAKE_API_ID=
expect 1 "api UID cannot be determined"         -- FAKE_API_UID=

if [ "$failures" -gt 0 ]; then
    echo "$failures case(s) failed" >&2
    exit 1
fi
echo "check-containers.sh: all checks passed"
