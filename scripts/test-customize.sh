#!/usr/bin/env bash
# Regression tests against throwaway fixtures, including after template customization.

set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }
expect_line() { grep -qxF "$2" "$1" || fail "expected value missing from $1"; }
snapshot() { find . -type f -print0 | sort -z | xargs -0 shasum | shasum; }

mkdir -p "$WORK/legacy/scripts" "$WORK/legacy/packages/config"
(
    cd "$WORK/legacy"
    cp "$ROOT/scripts/customize.sh" scripts/customize.sh
    cat > packages/config/branding.ts <<'TEMPLATE'
export const display = "{{APP_NAME}}";
export const host = "{{DOMAIN}}";
export const android = "{{ANDROID_PACKAGE}}";
export const ios = "{{IOS_BUNDLE_ID}}";
export const scheme = "{{DEEP_LINK_SCHEME}}";
TEMPLATE

    ./scripts/customize.sh 42_acme-app "Acme App" acme.example.com >/dev/null
    expect_line packages/config/branding.ts 'export const display = "Acme App";'
    expect_line packages/config/branding.ts 'export const host = "acme.example.com";'
    expect_line packages/config/branding.ts 'export const android = "com.example.app42acmeapp";'
    expect_line packages/config/branding.ts 'export const ios = "com.example.app42acmeapp";'
    expect_line packages/config/branding.ts 'export const scheme = "app-42-acme-app";'
    [[ ! -e apps/mobile ]] || fail "customize.sh created a missing mobile app"
)

mkdir "$WORK/flags"
cd "$WORK/flags"
mkdir -p scripts apps/api/app apps/web/node_modules/vendored apps/mobile/.expo packages/config
cp "$ROOT/scripts/customize.sh" scripts/customize.sh

cat > apps/api/app/__init__.py <<'TEMPLATE'
# {{DISPLAY_NAME}} API application package
TEMPLATE
cat > apps/api/.env.example <<'TEMPLATE'
SECRET_KEY={{GENERATE_SECRET_KEY}}
TEMPLATE
cat > apps/web/.env.example <<'TEMPLATE'
NEXT_PUBLIC_API_URL=http://localhost:8000
TEMPLATE
cat > apps/mobile/.env.example <<'TEMPLATE'
EXPO_PUBLIC_ANDROID_PACKAGE={{ANDROID_PACKAGE}}
EXPO_PUBLIC_IOS_BUNDLE_ID={{IOS_BUNDLE_ID}}
EXPO_PUBLIC_DEEP_LINK_SCHEME={{DEEP_LINK_SCHEME}}
EXPO_PUBLIC_APP_DOMAIN={{DOMAIN}}
TEMPLATE
cat > packages/config/branding.mjs <<'TEMPLATE'
export const project = "{{PROJECT_NAME}}";
TEMPLATE
printf '%s\n' 'name: {{PROJECT_NAME}}' > apps/web/node_modules/vendored/example.yaml
printf '%s\n' '{"slug":"{{PROJECT_NAME}}"}' > apps/mobile/.expo/settings.json

expect_invalid() {
    if ./scripts/customize.sh acme-app --display-name 'Acme App' "$@" > /dev/null 2>&1; then
        fail "accepted invalid option $1"
    fi
}

before=$(snapshot)
expect_invalid --display-name $'Broken\nName'
expect_invalid --domain 'https://acme.example.com'
expect_invalid --android-package 'com.42app'
expect_invalid --ios-bundle-id 'com.acme_app'
expect_invalid --deep-link-scheme 'acme://'
expect_invalid --domain
expect_invalid --unknown
[[ "$before" == "$(snapshot)" ]] || fail "invalid options modified files"

APP_NAME='Acme & Sons | Co/Ltd \ Group'
options=(acme-app --display-name "$APP_NAME" --domain acme.example.com
    --android-package com.acme.android --ios-bundle-id com.acme.ios-app --deep-link-scheme acme.app)
# Call from outside the fixture root to verify path resolution.
(cd apps/web && ../../scripts/customize.sh "${options[@]}" >/dev/null)

expect_line apps/api/app/__init__.py "# $APP_NAME API application package"
expect_line packages/config/branding.mjs 'export const project = "acme-app";'
expect_line apps/web/node_modules/vendored/example.yaml 'name: {{PROJECT_NAME}}'
expect_line apps/mobile/.expo/settings.json '{"slug":"{{PROJECT_NAME}}"}'
expect_line apps/api/.env.example 'SECRET_KEY={{GENERATE_SECRET_KEY}}'
grep -qE '^SECRET_KEY=[0-9a-f]{64}$' apps/api/.env || fail "API env has no generated secret"
cmp -s apps/web/.env.example apps/web/.env.local || fail "web env not copied"
cmp -s apps/mobile/.env.example apps/mobile/.env.local || fail "mobile env not copied"
expect_line apps/mobile/.env.local 'EXPO_PUBLIC_ANDROID_PACKAGE=com.acme.android'
expect_line apps/mobile/.env.local 'EXPO_PUBLIC_IOS_BUNDLE_ID=com.acme.ios-app'
expect_line apps/mobile/.env.local 'EXPO_PUBLIC_DEEP_LINK_SCHEME=acme.app'
expect_line apps/mobile/.env.local 'EXPO_PUBLIC_APP_DOMAIN=acme.example.com'

before=$(snapshot)
./scripts/customize.sh "${options[@]}" >/dev/null
[[ "$before" == "$(snapshot)" ]] || fail "second run modified files"

# Existing local env files are user-owned, even when they contain a template marker.
printf '%s\n' 'SECRET_KEY={{GENERATE_SECRET_KEY}}' > apps/api/.env
printf '%s\n' 'NEXT_PUBLIC_API_URL=http://localhost:9000' > apps/web/.env.local
printf '%s\n' 'EXPO_PUBLIC_DEEP_LINK_SCHEME=local-override' > apps/mobile/.env.local
before=$(snapshot)
./scripts/customize.sh "${options[@]}" >/dev/null
[[ "$before" == "$(snapshot)" ]] || fail "customize.sh modified existing env files"

echo "customize.sh: all checks passed"
