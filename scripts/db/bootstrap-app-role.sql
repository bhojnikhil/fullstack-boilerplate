-- Creates (or updates) the role the API connects as. Idempotent. Run it as a role that
-- may create roles (the database owner on most hosts), once per database server, before
-- the first migration:
--
--   psql "$MIGRATION_DATABASE_URL" -v ON_ERROR_STOP=1 \
--        -v app_role=app_user -v app_password='...' -f scripts/db/bootstrap-app-role.sql
--
-- The role must not own tables and must not be a superuser or have BYPASSRLS:
-- row-level security (migration 0004) only protects tenant data from roles it applies to.
-- Migrations run as the owner (MIGRATION_DATABASE_URL) and grant this role its table
-- access. `make db-bootstrap` runs this against the Compose database with a dev password.
--
-- Not for production secrets on a shared shell: the password appears in the process list.
-- Use your host's role management there (see docs/adr/0011-workspaces-and-rls.md).

SELECT format(
    'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'app_role', :'app_password'
) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'app_role') \gexec

SELECT format(
    'ALTER ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'app_role', :'app_password'
) \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_role') \gexec
