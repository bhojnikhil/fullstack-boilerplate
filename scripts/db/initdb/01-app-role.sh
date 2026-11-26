#!/bin/sh
# Runs once, when Compose initializes an empty Postgres volume (docker-entrypoint-initdb.d).
# Creates the non-owner role the API connects as. Existing volumes: `make db-bootstrap`.
# Development credentials only; real deployments create the role with their own secrets
# (docs/adr/0011-workspaces-and-rls.md).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v app_role="${APP_DB_ROLE:-app_user}" -v app_password="${APP_DB_PASSWORD:-app_user}" \
    -f /bootstrap-app-role.sql
