#!/usr/bin/env bash
# Regression test for scripts/customize.sh. Runs it on a throwaway copy of the
# repository (tracked + untracked, non-ignored files), never on the real tree.
#
# Usage: ./scripts/test-customize.sh

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

(cd "$ROOT" && git ls-files -z --cached --others --exclude-standard) \
    | (cd "$ROOT" && tar --null -T - -cf -) \
    | tar -xf - -C "$WORK"

cd "$WORK"
[ -f api/.env ] && fail "copy unexpectedly contains api/.env"

APP_NAME='Acme & Sons | Co/Ltd'
./scripts/customize.sh acme-app "$APP_NAME" acme.example.com >/dev/null

# 1. No template placeholders remain in source files.
if grep -rIl --exclude-dir=node_modules --exclude-dir=.git \
        --exclude=customize.sh --exclude=test-customize.sh \
        -E '\{\{(PROJECT_NAME|APP_NAME|DOMAIN)\}\}' . ; then
    fail "placeholders left in the files listed above"
fi

# 2. Values were substituted, including special characters in APP_NAME.
grep -q '^name = "acme-app-api"' api/pyproject.toml || fail "pyproject.toml name not replaced"
grep -q '"name": "acme-app-client"' client/package.json || fail "package.json name not replaced"
grep -qF "# $APP_NAME API application package" api/app/__init__.py || fail "APP_NAME not replaced literally"

# 3. Security regression: the generated secret goes ONLY into the untracked
#    api/.env; the tracked api/.env.example keeps its placeholder.
grep -q '^SECRET_KEY={{GENERATE_SECRET_KEY}}$' api/.env.example \
    || fail "api/.env.example was modified (a secret would be committed)"
grep -qE '^SECRET_KEY=[0-9a-f]{64}$' api/.env || fail "api/.env has no generated SECRET_KEY"
[ -f client/.env.local ] || fail "client/.env.local not created"

# 4. Idempotent: a second run changes nothing (including the secret).
snapshot() { find . -path ./node_modules -prune -o -type f ! -path './.git/*' -print0 | sort -z | xargs -0 shasum | shasum; }
before=$(snapshot)
./scripts/customize.sh acme-app "$APP_NAME" acme.example.com >/dev/null
after=$(snapshot)
[ "$before" = "$after" ] || fail "second run modified files (not idempotent)"

echo "customize.sh: all checks passed"
