# Changelog

All notable changes to this boilerplate. Format: [Keep a Changelog](https://keepachangelog.com/).
Versions are tagged by the maintainer; nothing is tagged or released automatically.

## [2.0.0] - Unreleased

A ground-up upgrade of v1. Breaking: this is a new project layout, schema and API.

### Added

- **Monorepo**: `apps/api`, `apps/web`, `apps/mobile`, `packages/api-client`, `packages/config`;
  uv for Python, pnpm + Turborepo for JavaScript (ADR 0001, 0002).
- **API**: async SQLAlchemy 2.1 + psycopg 3, request unit of work, error envelope, Alembic-only
  schema, `/v1`, cursor pagination, idempotency keys, `/health` and `/ready`, version gate and
  `/v1/meta` (ADR 0004, 0014, 0018).
- **Auth redesign**: argon2id passwords, email verification, password reset, short-lived access
  JWTs with rotating refresh tokens and session management, step-up re-authentication,
  Sign in with Google by ID token with safe account linking, Postgres rate limits, audit log,
  account deletion (ADR 0008 to 0010).
- **Multi-tenancy**: workspaces, memberships (owner/admin/member), invitations, Postgres
  row-level security with a non-owner application role, tenant isolation test suite (ADR 0016).
- **Jobs and integrations**: Postgres job queue and worker, email (console/SMTP/Resend, Mailpit),
  Expo push, S3/R2 presigned URLs, Sentry (ADR 0013, 0014).
- **API client**: OpenAPI export and generated TypeScript client with a CI drift check (ADR 0012).
- **Web**: Next.js 16 rebuild with shadcn/ui, auth, workspace, invitation, items and account
  flows, public legal and account-deletion pages, App/Universal Links association files,
  Vitest and Playwright (ADR 0005).
- **Mobile**: Expo SDK 58 app with auth, items and an offline write queue, workspaces and
  invitations, push, biometric lock, EAS profiles and `pnpm release:update` (ADR 0006, 0007, 0015).
- **DevOps**: path-filtered CI with a `CI gate`, security workflow (gitleaks, dependency review,
  pip-audit, pnpm audit), pre-commit, Fly.io + Neon + Vercel deploy workflow, manual mobile
  release workflow, Neon preview branches (all skip without secrets) (ADR 0011, 0017).
- `scripts/customize.sh` for the new layout, `make seed`, `AGENTS.md`, `docs/deploy.md`.

### Fixed (v1 defects)

OAuth state/CSRF flow removed; pre-account-takeover via email linking; JWT in redirect URL;
insecure default secret; long-lived unrevocable sessions and missing rate limits; stored Google
tokens; `create_all` migration bypass; per-call commits and HTTP in services; broken Docker
healthcheck; committed `.pyc`/DB files; README claims that did not match the code.

### Not verified

Real Google sign-in, real email/push delivery, S3/R2, EAS builds, Play submission and any cloud
deploy have never been run. See the README's "Shipping to Google Play" and `docs/deploy.md`.
