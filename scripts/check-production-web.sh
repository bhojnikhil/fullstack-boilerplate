#!/usr/bin/env bash
# Verify public responses from the packaged web server started by make smoke.
set -euo pipefail

base_url="http://127.0.0.1:${WEB_PORT:-3000}"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fail() { printf '%s\n' "$*" >&2; exit 1; }

check_association() {
    local path=$1 expected=$2 status
    status=$(curl --silent --show-error --max-time 10 --dump-header "$work/headers" \
        --output "$work/body" --write-out '%{http_code}' "${base_url}${path}")
    [ "$status" = 200 ] || fail "$path returned HTTP $status, expected 200 without redirects"
    grep -Eiq '^content-type: application/json([;[:space:]]|$)' "$work/headers" \
        || fail "$path is missing the application/json content type"
    grep -Fq "$expected" "$work/body" || fail "$path is missing its runtime app ID"
}

check_page() {
    local path=$1 expected=$2
    curl --fail --silent --show-error --max-time 10 "$base_url$path" --output "$work/body"
    # React inserts comment nodes between adjacent text segments during SSR.
    sed 's/<!-- -->//g' "$work/body" > "$work/page"
    grep -Fq "$expected" "$work/page" || fail "$path is missing its runtime settings"
}

check_association /.well-known/assetlinks.json '"package_name":"com.example.smoke"'
check_association /.well-known/apple-app-site-association '"ABCDE12345.com.example.smoke"'
check_page /account-deletion 'href="mailto:deletion@smoke.example.com?subject=Account%20deletion%20request"'
check_page /privacy 'operates Compose runtime smoke app at '

echo "Web smoke passed for the association JSON and runtime settings on public pages."
