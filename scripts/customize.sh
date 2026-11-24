#!/usr/bin/env bash
# Replace template placeholders with your project's values.
#
# Usage: ./scripts/customize.sh PROJECT_NAME "App Name" [DOMAIN]
#
# - Replaces {{PROJECT_NAME}}, {{APP_NAME}} and {{DOMAIN}} in text files
#   (skips .git, node_modules, .venv, .next and other generated directories).
# - Creates apps/api/.env and apps/web/.env.local from their .env.example files if
#   they do not exist, and writes a freshly generated SECRET_KEY into apps/api/.env
#   ONLY. The tracked .env.example files keep their placeholders, so no secret
#   ever lands in a committed file.
# - Safe to re-run: files without placeholders are left untouched and existing
#   .env files are never overwritten.
# - Works with both GNU sed (Linux) and BSD sed (macOS).

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

usage() {
    echo "Usage: ./scripts/customize.sh PROJECT_NAME APP_NAME [DOMAIN]"
    echo ""
    echo "  PROJECT_NAME  Lowercase project name (a-z, 0-9, -, _), e.g. myapp"
    echo "  APP_NAME      Display name, e.g. 'My App'"
    echo "  DOMAIN        Production domain (optional, default: localhost)"
}

if [ $# -lt 2 ]; then
    printf "${RED}Error: missing required arguments${NC}\n\n"
    usage
    exit 1
fi

PROJECT_NAME=$1
APP_NAME=$2
DOMAIN=${3:-localhost}

if ! [[ "$PROJECT_NAME" =~ ^[a-z0-9_-]+$ ]]; then
    printf "${RED}Error: PROJECT_NAME must be lowercase alphanumeric (a-z, 0-9, -, _)${NC}\n"
    exit 1
fi

# Run from the repository root regardless of the caller's working directory.
cd "$(dirname "$0")/.."

# In-place sed that works on GNU and BSD sed.
sed_inplace() {
    if sed --version >/dev/null 2>&1; then
        sed -i "$@"
    else
        sed -i '' "$@"
    fi
}

# Escape a value for use as a sed replacement (handles \, & and the | delimiter).
sed_escape() {
    printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

printf "${YELLOW}Customizing:${NC} project=%s app='%s' domain=%s\n" "$PROJECT_NAME" "$APP_NAME" "$DOMAIN"

PROJECT_ESC=$(sed_escape "$PROJECT_NAME")
APP_ESC=$(sed_escape "$APP_NAME")
DOMAIN_ESC=$(sed_escape "$DOMAIN")

count=0
while IFS= read -r -d '' file; do
    if grep -qE '\{\{(PROJECT_NAME|APP_NAME|DOMAIN)\}\}' "$file"; then
        sed_inplace \
            -e "s|{{PROJECT_NAME}}|${PROJECT_ESC}|g" \
            -e "s|{{APP_NAME}}|${APP_ESC}|g" \
            -e "s|{{DOMAIN}}|${DOMAIN_ESC}|g" \
            "$file"
        echo "  updated ${file#./}"
        count=$((count + 1))
    fi
done < <(
    find . \
        \( -name .git -o -name node_modules -o -name .venv -o -name venv \
           -o -name .next -o -name .turbo -o -name dist -o -name build -o -name __pycache__ \
           -o -name .mypy_cache -o -name .ruff_cache -o -name .pytest_cache \) -prune \
        -o -type f \
        \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' \
           -o -name '*.json' -o -name '*.yaml' -o -name '*.yml' -o -name '*.toml' \
           -o -name '*.md' -o -name '.env.example' -o -name 'Dockerfile*' -o -name 'Makefile' \) \
        ! -path './scripts/customize.sh' \
        -print0
)
printf "${GREEN}✓${NC} Replaced placeholders in %d file(s)\n" "$count"

# --- Local env files (untracked) --------------------------------------------
if [ ! -f apps/api/.env ]; then
    cp apps/api/.env.example apps/api/.env
    echo "  created apps/api/.env"
fi
if grep -q '{{GENERATE_SECRET_KEY}}' apps/api/.env; then
    SECRET_KEY=$(openssl rand -hex 32)
    sed_inplace -e "s|{{GENERATE_SECRET_KEY}}|${SECRET_KEY}|g" apps/api/.env
    echo "  generated SECRET_KEY in apps/api/.env"
fi

if [ ! -f apps/web/.env.local ]; then
    cp apps/web/.env.example apps/web/.env.local
    echo "  created apps/web/.env.local"
fi

printf "${GREEN}✓ Done.${NC}\n\n"
echo "Next steps:"
echo "  1. Review apps/api/.env and apps/web/.env.local"
echo "  2. make up            # postgres, api, web"
echo "  3. Open http://localhost:3000/auth/register to create a user"
