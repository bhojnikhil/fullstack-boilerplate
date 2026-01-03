#!/bin/bash

# Full-Stack Boilerplate Customization Script
# Usage: ./scripts/customize.sh myapp "My App" mydomain.com

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check arguments
if [ $# -lt 2 ]; then
    echo -e "${RED}Error: Missing required arguments${NC}"
    echo ""
    echo "Usage: ./scripts/customize.sh PROJECT_NAME APP_NAME [DOMAIN]"
    echo ""
    echo "Arguments:"
    echo "  PROJECT_NAME  Lowercase project name (e.g., myapp, todo-app)"
    echo "  APP_NAME      Display name (e.g., 'My App', 'Todo App')"
    echo "  DOMAIN        Production domain (optional, e.g., myapp.com)"
    echo ""
    echo "Examples:"
    echo "  ./scripts/customize.sh myapp 'My App'"
    echo "  ./scripts/customize.sh todo-app 'Todo App' todo-app.com"
    exit 1
fi

PROJECT_NAME=$1
APP_NAME=$2
DOMAIN=${3:-localhost}

# Validate project name
if ! [[ "$PROJECT_NAME" =~ ^[a-z0-9_-]+$ ]]; then
    echo -e "${RED}Error: PROJECT_NAME must be lowercase alphanumeric (a-z, 0-9, -, _)${NC}"
    exit 1
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     Full-Stack Boilerplate - Customization Script              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Customizing for:${NC}"
echo -e "  ${GREEN}Project Name: ${PROJECT_NAME}${NC}"
echo -e "  ${GREEN}App Name: ${APP_NAME}${NC}"
echo -e "  ${GREEN}Domain: ${DOMAIN}${NC}"
echo ""

# Generate SECRET_KEY
SECRET_KEY=$(openssl rand -hex 32)
echo -e "${GREEN}✓${NC} Generated SECRET_KEY"

# Find and replace all placeholders
echo ""
echo -e "${YELLOW}Replacing placeholders...${NC}"

# Files to update
FILES_TO_UPDATE=$(find . -type f \
  \( \
    -name "*.py" -o \
    -name "*.ts" -o \
    -name "*.tsx" -o \
    -name "*.js" -o \
    -name "*.jsx" -o \
    -name "*.json" -o \
    -name "*.yaml" -o \
    -name "*.yml" -o \
    -name "*.md" -o \
    -name ".env*" -o \
    -name "Dockerfile*" -o \
    -name "Caddyfile" \
  \) \
  ! -path "./.git/*" \
  ! -path "./node_modules/*" \
  ! -path "./.next/*" \
  ! -path "./dist/*" \
)

# Replace PROJECT_NAME
echo "  - Replacing {{PROJECT_NAME}} with ${PROJECT_NAME}"
for file in $FILES_TO_UPDATE; do
    if [ -f "$file" ]; then
        sed -i '' "s/{{PROJECT_NAME}}/${PROJECT_NAME}/g" "$file" 2>/dev/null || true
    fi
done

# Replace APP_NAME
echo "  - Replacing {{APP_NAME}} with ${APP_NAME}"
for file in $FILES_TO_UPDATE; do
    if [ -f "$file" ]; then
        sed -i '' "s/{{APP_NAME}}/${APP_NAME}/g" "$file" 2>/dev/null || true
    fi
done

# Replace DOMAIN
echo "  - Replacing {{DOMAIN}} with ${DOMAIN}"
for file in $FILES_TO_UPDATE; do
    if [ -f "$file" ]; then
        sed -i '' "s/{{DOMAIN}}/${DOMAIN}/g" "$file" 2>/dev/null || true
    fi
done

# Replace SECRET_KEY in .env files
echo "  - Replacing {{GENERATE_SECRET_KEY}} with generated key"
ENV_FILES=$(find . -name ".env*" ! -path "./.git/*" ! -path "./node_modules/*")
for file in $ENV_FILES; do
    if [ -f "$file" ]; then
        sed -i '' "s/{{GENERATE_SECRET_KEY}}/${SECRET_KEY}/g" "$file" 2>/dev/null || true
    fi
done

echo -e "${GREEN}✓${NC} Placeholders replaced"

# Create .env files if they don't exist
echo ""
echo -e "${YELLOW}Creating environment files...${NC}"

if [ ! -f "api/.env" ]; then
    cp "api/.env.example" "api/.env"
    echo -e "${GREEN}✓${NC} Created api/.env"
else
    echo -e "${GREEN}✓${NC} api/.env already exists"
fi

if [ ! -f "client/.env.local" ]; then
    cp "client/.env.local.example" "client/.env.local"
    echo -e "${GREEN}✓${NC} Created client/.env.local"
else
    echo -e "${GREEN}✓${NC} client/.env.local already exists"
fi

if [ ! -f "infra/.env" ]; then
    cp "infra/.env.example" "infra/.env"
    echo -e "${GREEN}✓${NC} Created infra/.env"
else
    echo -e "${GREEN}✓${NC} infra/.env already exists"
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     ✓ Customization Complete!                                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Next Steps:${NC}"
echo ""
echo "1. ${GREEN}Configure environment variables:${NC}"
echo "   - api/.env (Database, JWT, Google OAuth)"
echo "   - client/.env.local (API URL)"
echo "   - infra/.env (Database, domain)"
echo ""
echo "2. ${GREEN}Install pre-commit hooks:${NC}"
echo "   pre-commit install"
echo ""
echo "3. ${GREEN}Start development environment:${NC}"
echo "   make up"
echo ""
echo "4. ${GREEN}Visit your app:${NC}"
echo "   Frontend: http://localhost:3000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "5. ${GREEN}Create first user:${NC}"
echo "   Visit http://localhost:3000/login and sign up"
echo ""
echo -e "${YELLOW}Documentation:${NC}"
echo "  - SETUP.md - Detailed setup guide"
echo "  - CUSTOMIZATION.md - How to customize for your needs"
echo "  - ARCHITECTURE.md - Technical architecture"
echo "  - DEPLOYMENT.md - Deployment guide"
echo ""
echo -e "${GREEN}Happy building! 🚀${NC}"
echo ""
