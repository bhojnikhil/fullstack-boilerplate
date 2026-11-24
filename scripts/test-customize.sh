#!/usr/bin/env bash
# Regression test for scripts/customize.sh.
#
# Runs the script against a minimal, self-contained template fixture built in a
# temp directory, never against the real tree. The fixture supplies its own
# placeholders, so this test keeps passing after a project has been customized
# (when the repository itself no longer contains any placeholders).
#
# Usage: ./scripts/test-customize.sh

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

# ---- Fixture ----------------------------------------------------------------
cd "$WORK"
mkdir -p scripts apps/api/app apps/web/node_modules/some-pkg
cp "$ROOT/scripts/customize.sh" scripts/customize.sh

cat > apps/api/pyproject.toml <<'EOF'
[project]
name = "{{PROJECT_NAME}}-api"
EOF
cat > apps/api/app/__init__.py <<'EOF'
# {{APP_NAME}} API application package
EOF
cat > apps/api/.env.example <<'EOF'
SECRET_KEY={{GENERATE_SECRET_KEY}}
EOF
cat > apps/web/package.json <<'EOF'
{
  "name": "{{PROJECT_NAME}}-client"
}
EOF
cat > apps/web/.env.example <<'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
EOF
cat > README.md <<'EOF'
Visit https://{{DOMAIN}}
EOF
# Generated/vendored directories must never be modified.
cat > apps/web/node_modules/some-pkg/package.json <<'EOF'
{ "name": "{{PROJECT_NAME}}" }
EOF

# ---- Run ----------------------------------------------------------------------
APP_NAME='Acme & Sons | Co/Ltd'
./scripts/customize.sh acme-app "$APP_NAME" acme.example.com >/dev/null

# 1. No template placeholders remain in source files (vendored dirs excluded).
if grep -rIl --exclude-dir=node_modules --exclude=customize.sh \
        -E '\{\{(PROJECT_NAME|APP_NAME|DOMAIN)\}\}' . ; then
    fail "placeholders left in the files listed above"
fi

# 2. Values were substituted, including special characters in APP_NAME.
grep -qx 'name = "acme-app-api"' apps/api/pyproject.toml || fail "pyproject.toml name not replaced"
grep -q '"name": "acme-app-client"' apps/web/package.json || fail "package.json name not replaced"
grep -qxF "# $APP_NAME API application package" apps/api/app/__init__.py || fail "APP_NAME not replaced literally"
grep -qx 'Visit https://acme.example.com' README.md || fail "DOMAIN not replaced"

# 3. node_modules is left alone.
grep -q '{{PROJECT_NAME}}' apps/web/node_modules/some-pkg/package.json \
    || fail "customize.sh modified files under node_modules"

# 4. Security regression: the generated secret goes ONLY into the untracked
#    apps/api/.env; the tracked apps/api/.env.example keeps its placeholder.
grep -qx 'SECRET_KEY={{GENERATE_SECRET_KEY}}' apps/api/.env.example \
    || fail "apps/api/.env.example was modified (a secret would be committed)"
grep -qE '^SECRET_KEY=[0-9a-f]{64}$' apps/api/.env || fail "apps/api/.env has no generated SECRET_KEY"
[ -f apps/web/.env.local ] || fail "apps/web/.env.local not created"

# 5. Idempotent: a second run changes nothing (including the secret).
snapshot() { find . -type f -print0 | sort -z | xargs -0 shasum | shasum; }
before=$(snapshot)
./scripts/customize.sh acme-app "$APP_NAME" acme.example.com >/dev/null
after=$(snapshot)
[ "$before" = "$after" ] || fail "second run modified files (not idempotent)"

echo "customize.sh: all checks passed"
