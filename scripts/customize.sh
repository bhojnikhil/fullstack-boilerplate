#!/usr/bin/env bash
# Replace template placeholders and initialize missing local environment files.

set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: ./scripts/customize.sh PROJECT_NAME [APP_NAME [DOMAIN]] [options]

  PROJECT_NAME               Lowercase project name (a-z, 0-9, -, _)
  --display-name NAME        Display name (required if APP_NAME is omitted)
  --domain HOSTNAME          Domain without scheme or port (default: localhost)
  --android-package ID       Android application ID (default: com.example.<project>)
  --ios-bundle-id ID         iOS bundle identifier (default: com.example.<project>)
  --deep-link-scheme SCHEME   Lowercase URI scheme (default: derived from PROJECT_NAME)
  -h, --help                 Show this help
USAGE
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

if [[ "${1:-}" == --help || "${1:-}" == -h ]]; then
    usage
    exit 0
fi
[[ $# -gt 0 ]] || die "PROJECT_NAME is required. See --help."

project=$1
shift
[[ "$project" =~ ^[a-z0-9_-]+$ ]] || die "PROJECT_NAME must use a-z, 0-9, - or _."

display=''
domain=localhost
# Keep the original positional form working alongside the named options.
if [[ $# -gt 0 && "$1" != -* ]]; then
    display=$1
    shift
fi
if [[ $# -gt 0 && "$1" != -* ]]; then
    domain=$1
    shift
fi

app_id="${project//[-_]/}"
[[ "$app_id" =~ ^[a-z] ]] || app_id="app$app_id"
android_package="com.example.$app_id"
ios_bundle_id="com.example.$app_id"
deep_link_scheme="${project//_/-}"
[[ "$deep_link_scheme" =~ ^[a-z] ]] || deep_link_scheme="app-$deep_link_scheme"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help) usage; exit 0 ;;
        --display-name|--domain|--android-package|--ios-bundle-id|--deep-link-scheme)
            [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || die "$1 requires a value."
            case "$1" in
                --display-name) display=$2 ;;
                --domain) domain=$2 ;;
                --android-package) android_package=$2 ;;
                --ios-bundle-id) ios_bundle_id=$2 ;;
                --deep-link-scheme) deep_link_scheme=$2 ;;
            esac
            shift 2
            ;;
        *) die "Unknown argument: $1. See --help." ;;
    esac
done

[[ "$display" =~ [^[:space:]] && "$display" != *$'\n'* && "$display" != *$'\r'* && "$display" != *'{{'* ]] \
    || die "Display name must be nonblank, on one line, and contain no template markers."
# The display name lands in Next.js and Compose dotenv files (double-quoted) and in
# Expo's dotenv: keep it literal in all of them.
case "$display" in
    *'\'*|*'"'*|*'$'*|*'`'*)
        die "Display name cannot contain backslashes, double quotes, dollar signs or backticks."
        ;;
esac
host_label='[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
[[ ${#domain} -le 253 && "$domain" =~ ^$host_label(\.$host_label)*$ ]] \
    || die "Domain must be a hostname without a scheme, port or path."
[[ "$android_package" =~ ^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$ ]] \
    || die "Android package must contain at least two dot-separated identifiers starting with letters."
[[ "$ios_bundle_id" =~ ^[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)+$ ]] \
    || die "iOS bundle ID must contain at least two dot-separated components using letters, digits or hyphens."
[[ "$deep_link_scheme" =~ ^[a-z][a-z0-9+.-]*$ ]] \
    || die "Deep-link scheme must start with a lowercase letter and use a-z, 0-9, +, . or -."

# Run from the repository root regardless of the caller's working directory.
cd "$(dirname "$0")/.."

# BSD sed requires an explicit backup suffix for in-place edits.
if sed --version >/dev/null 2>&1; then
    inplace=(-i)
else
    inplace=(-i '')
fi

sed_escape() {
    printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

display_escaped=$(sed_escape "$display")
tokens='\{\{(PROJECT_NAME|APP_NAME|DISPLAY_NAME|DOMAIN|ANDROID_PACKAGE|IOS_BUNDLE_ID|DEEP_LINK_SCHEME)\}\}'

while IFS= read -r -d '' file; do
    if grep -qE "$tokens" "$file"; then
        sed "${inplace[@]}" \
            -e "s|{{PROJECT_NAME}}|$project|g" \
            -e "s|{{DISPLAY_NAME}}|$display_escaped|g" \
            -e "s|{{APP_NAME}}|$display_escaped|g" \
            -e "s|{{DOMAIN}}|$domain|g" \
            -e "s|{{ANDROID_PACKAGE}}|$android_package|g" \
            -e "s|{{IOS_BUNDLE_ID}}|$ios_bundle_id|g" \
            -e "s|{{DEEP_LINK_SCHEME}}|$deep_link_scheme|g" \
            "$file"
        printf '  updated %s\n' "${file#./}"
    fi
done < <(
    find . \
        \( -name .git -o -name node_modules -o -name .pnpm-store -o -name .venv \
           -o -name venv -o -name .next -o -name .turbo -o -name .expo \
           -o -name dist -o -name build -o -name out -o -name coverage -o -name htmlcov \
           -o -name __pycache__ -o -name .mypy_cache -o -name .ruff_cache \
           -o -name .pytest_cache -o -name .tmp -o -name tmp \) -prune \
        -o -type f \
        \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \
           -o -name '*.mjs' -o -name '*.cjs' -o -name '*.json' -o -name '*.yaml' \
           -o -name '*.yml' -o -name '*.toml' -o -name '*.md' -o -name '.env.example' \
           -o -name '.env.*.example' -o -name 'Dockerfile*' -o -name 'Makefile' \) \
        ! -name boilerplate-v2-prompt.md ! -name boilerplate-v2-phase-prompts.md \
        -print0
)

create_env() {
    local template=$1 target=$2 secret
    [[ -f "$template" && ! -e "$target" && ! -L "$target" ]] || return 0

    if [[ "$target" == apps/api/.env ]] && grep -qF '{{GENERATE_SECRET_KEY}}' "$template"; then
        secret=$(openssl rand -hex 32)
        (umask 077; set -C; sed "s|{{GENERATE_SECRET_KEY}}|$secret|g" "$template" > "$target")
    else
        (umask 077; set -C; cat "$template" > "$target")
    fi
    printf '  created %s\n' "$target"
}

create_env apps/api/.env.example apps/api/.env
create_env apps/web/.env.example apps/web/.env.local
# Expo CLI and app.config.ts read apps/mobile/.env (not .env.local).
create_env apps/mobile/.env.example apps/mobile/.env
