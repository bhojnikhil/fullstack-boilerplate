#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
(cd apps/api && PYTHONPATH=. "${UV:-uv}" run --locked python ../../scripts/export-openapi.py)
pnpm exec openapi-typescript packages/api-client/openapi.json -o packages/api-client/src/schema.d.ts
pnpm exec prettier --write packages/api-client/openapi.json packages/api-client/src/schema.d.ts
