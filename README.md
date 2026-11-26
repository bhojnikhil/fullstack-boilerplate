# Full-Stack Boilerplate

A starter monorepo with a **FastAPI** backend (`apps/api`), a **Next.js 16** frontend
(`apps/web`) and an **Expo** (React Native) mobile app foundation (`apps/mobile`). It uses
uv for Python and pnpm workspaces + Turborepo for JavaScript, runs locally with Docker
Compose, and is tested in GitHub Actions.

> [!WARNING]
> **Not production-ready yet.** A v2 upgrade (multi-tenancy, background jobs, mobile app,
> web rebuild, real deploys) is in progress as a series of PRs. Gaps in the current code:
>
> - The web app has email verification, but the forgot-password, reset-password and
>   confirm-email pages are planned for phase 8b. Until then, post those emailed tokens
>   to the API (see [Authentication](#authentication)).
> - Email, push and cleanup need the `worker` process (`python -m app.jobs`) to be running;
>   without it, messages wait in the `jobs` table. Real Resend/SMTP delivery, Expo push and
>   S3/R2 presigned URLs have not been exercised against the live services (see below).
> - The web app has no Google sign-in button yet (the API endpoint exists).

## Repository layout

```
apps/
  api/            FastAPI service (Python, uv)
  web/            Next.js app (pnpm workspace package "web")
  mobile/         Expo (React Native) app (pnpm workspace package "mobile")
packages/
  config/         shared TypeScript, ESLint and Prettier config (@repo/config)
docs/adr/         architecture decision records
scripts/          customize.sh and regression tests for repo tooling
Makefile          single entry point for both Python and JS tasks (`make help`)
```

## What's included

**Backend (`apps/api`)**

- Python 3.13, FastAPI, async SQLAlchemy 2.1, psycopg 3 and PostgreSQL 16.
- Router → Service → Repository layers in `app/modules/auth` and `app/modules/items`.
  The request session commits after the response is prepared and rolls back on errors.
- Accounts and authentication ([details](#authentication)): email/password with argon2id,
  email verification, password reset, Sign in with Google by ID token, 15-minute access
  JWTs with rotating refresh tokens per device session, session management, step-up
  re-authentication, account deletion, Postgres-backed rate limiting and an audit log.
- Email through a small provider interface: console (development), SMTP, Resend, and an
  in-memory backend for tests. Compose runs [Mailpit](https://mailpit.axllent.org/) to
  view messages locally.
- Background jobs ([ADR 0011](docs/adr/0011-postgres-job-queue.md)): a Postgres job table
  (`FOR UPDATE SKIP LOCKED`) with retries and backoff, run by a separate worker
  (`python -m app.jobs`, the `worker` Compose service). Emails are enqueued in the
  request's transaction, so a rolled-back request sends nothing. Periodic jobs process push
  receipts (15 min) and purge expired sessions, refresh tokens, emailed tokens, idempotency
  records, rate-limit rows and old dead jobs (hourly).
- Push ([ADR 0012](docs/adr/0012-push-storage-version-gate-sentry.md)): `POST`/`DELETE
/v1/devices` register and remove Expo push tokens; jobs send through the Expo Push API
  and prune tokens that receipts report as `DeviceNotRegistered`.
- S3-compatible storage interface (S3, R2, MinIO) with presigned upload/download URLs and
  type/size limits. No endpoint uses it yet.
- `GET /v1/meta` and a `426 app_update_required` gate for mobile clients below
  `MIN_SUPPORTED_APP_VERSION` (`X-App-Version`/`X-Platform` headers; web is never gated).
- Sentry for the API and worker when `SENTRY_DSN` is set; no personal data is sent.
- User-scoped item CRUD at `/v1/items`, with cursor pagination and optional
  idempotency keys on signed-in mutations. The OpenAPI operation IDs use the module
  and handler names.
- JSON error envelopes, environment-based CORS and trusted hosts, restrictive response
  headers and a configurable request body limit. Request logs use route templates and
  include request ID, method, status, duration and the user ID when available. Exception
  logs include structured stack frames and exception types, with messages and locals omitted.
  Development uses console logs with a redacted traceback; other environments use JSON.
- `GET /health` checks liveness without Postgres. `GET /ready` checks DB connectivity
  and the applied Alembic revision. Both probes accept the platform's Host header,
  including the container's loopback Host. The host allowlist applies to other routes.
- Dependencies managed with uv: exact pins in `pyproject.toml`, locked in `uv.lock`
  ([ADR 0001](docs/adr/0001-python-tooling-uv.md)).

**Frontend (`apps/web`)**

- Next.js 16 (App Router), React 19, TypeScript 6 (`strict`), extending the shared
  config in `packages/config`.
- Public pages at `/`, `/privacy`, `/terms`, and `/account-deletion`. Sign-in, registration
  and sample items at `/auth/login`, `/auth/register`, and `/items`.
- Tailwind CSS 4 and shadcn/ui button, input and label components. The site theme follows
  the operating system by default and remembers an explicit light or dark selection.
- Android App Links and Apple Universal Links association documents at `/.well-known/`.
- Vitest with React Testing Library and a Playwright Chromium smoke suite for the public site.
- axios API client (`lib/api.ts`) that keeps the access token in memory, refreshes it
  silently with the httpOnly refresh cookie and CSRF token (one refresh at a time across
  tabs where the Web Locks API exists), and sends `X-Platform: web`. Zustand auth store
  (`lib/auth-store.ts`).

**Mobile (`apps/mobile`)**: see [Mobile](#mobile). Sign-in and sign-up with email
verification, email-link screens, native Google sign-in (development build), items with an
offline write queue, sessions, profile, account deletion, biometric lock and push
registration. Workspace, members and invitation screens are written against an **assumed**
API contract because phase 5 is not merged yet (see below).

- Expo SDK 58, React Native 0.88, TypeScript 6 (`strict` plus the shared
  `packages/config` options), Expo Router with `(auth)` and `(app)` route groups and
  screens for auth, items, workspaces and settings.
- Styling with React Native `StyleSheet` and typed light/dark design tokens
  ([ADR 0006](docs/adr/0006-mobile-styling.md)).
- `app.config.ts` driven by environment variables, `eas.json` build profiles and EAS
  Update channels. Nothing has been built with EAS yet.
- Jest + React Native Testing Library tests; `expo-doctor` in CI.

**Tooling**

- pnpm workspaces + Turborepo for `lint`, `typecheck`, `test`, `build`, `dev`
  ([ADR 0002](docs/adr/0002-js-monorepo-pnpm-turborepo.md)).
- Formatting: ruff format (Python) and Prettier (`apps/web`, `apps/mobile`, `packages`),
  both enforced in CI.
- Docker images ([ADR 0003](docs/adr/0003-container-images.md)):
  - API: multi-stage; the default `runtime` target is slim (no compilers, uv, pip or
    tests) and runs as an unprivileged user; a `dev` target is used by Compose.
  - Web: Next.js standalone server, running as the unprivileged `node` user.
  - Both have `HEALTHCHECK`s that require a 2xx response and don't follow redirects.
- `docker-compose.yml`: `postgres`, `api` (`dev` target, hot reload, source mounted),
  `worker` (same image, `python -m app.jobs`, no reload), `web` (production build; rebuild to see changes, or use `make dev` for hot reload) and
  `mailpit` (SMTP on 1025, inbox UI on 8025). The API sends its email to Mailpit.
- `apps/api/.dockerignore` and `apps/web/Dockerfile.dockerignore` keep env files, keys
  and local DBs (at any depth) out of images.
- GitHub Actions (`.github/workflows/ci.yml`, which calls `mobile.yml`), with every third-party
  action pinned to a commit SHA:
  - **api**: locked uv install, Ruff lint and format, strict mypy, Alembic upgrade and
    drift check, and pytest on Postgres 16 with a 96.0% branch-aware coverage gate.
  - **web**: `pnpm install --frozen-lockfile`, Prettier check, then ESLint, `tsc` and
    `next build` via Turborepo (ESLint and `tsc` run for every JS package, including
    mobile), Vitest, and Playwright against the standalone build;
  - **scripts**: `scripts/test-customize.sh`, `scripts/test-check-containers.sh`;
  - **docker**: `scripts/test-dockerignore.sh`, build all images, then start postgres,
    mailpit, api, worker and web as packaged, and require all to be healthy. The API smoke uses
    production settings, temporary signing keys and a host allowlist that excludes
    loopback. It checks HSTS, JSON logs, startup failure without `SECRET_KEY` or
    `JWT_SECRET_KEY`, and a sign-up whose verification email is queued, sent by the worker over
    SMTP to Mailpit, verified, and followed by a web sign-in that sets a `Secure`, `HttpOnly`,
    `SameSite=Strict` refresh cookie. CI requires `/ready` to return HTTP 503 before
    explicit migrations and 2xx afterward. The web smoke requires direct 200 JSON
    responses and one-hour cache headers from both association URLs. It checks security
    headers and the runtime values in the privacy and account deletion pages. The API and
    web must run as unprivileged users with no mounts. Locally use `make smoke`.
  - **mobile** (`mobile.yml`, called by `ci.yml` only when `apps/mobile`, `packages`, the lockfile or root
    JS config change): Prettier check, `tsc`, ESLint, Jest and `expo-doctor`, each as
    its own step.
- Dependabot groups weekly updates for uv, pnpm, Dockerfiles, Compose and GitHub Actions.
- Deploy and release workflows (`deploy.yml`, `mobile-release.yml`, `neon-preview.yml`)
  skip with a notice when their secrets are absent. **Nothing has been deployed or
  released from this repository**; see [docs/deploy.md](docs/deploy.md).
- CI is path-filtered: a `changes` job decides which of api, web, mobile, scripts and
  docker run, and the `CI gate` job (the check to require in branch protection) fails
  if any of them failed. Security and Pre-commit are separate workflows that always run.

## Quick start (Docker)

Prerequisites: Docker with Compose v2 (`docker compose`), Make, Git, OpenSSL.

```bash
git clone https://github.com/bhojnikhil/fullstack-boilerplate myapp
cd myapp

# Fill in template placeholders
# and create apps/api/.env (with a generated SECRET_KEY) and apps/web/.env.local.
./scripts/customize.sh myapp "My App" myapp.com

make up
```

Then open:

- Web: http://localhost:3000. Create a user at `/auth/register`.
- Mailpit: http://localhost:8025. Verification and other emails land here.
- API docs (Swagger UI): http://localhost:8000/docs (ReDoc: `/redoc`)

`make up` waits for Postgres and runs Alembic in a one-off container before starting
the API and web. If you start services with Compose directly, run `make migrate-compose`
to apply migrations. The Compose development API bind-mounts `apps/api` and reads its
`.env`, with Compose's service environment taking precedence. The packaged image reads
its process environment.

Compose publishes Postgres, the API, the web app and Mailpit on IPv4 loopback
(`127.0.0.1`) only, on host ports 5432, 8000, 3000, 8025 (Mailpit UI) and 1025 (Mailpit
SMTP) by default. Set `POSTGRES_PORT`, `API_PORT`, `WEB_PORT`, `MAILPIT_UI_PORT` and
`MAILPIT_SMTP_PORT` on the command line if those ports are in use.

### Customizing project identity

```bash
./scripts/customize.sh myapp \
  --display-name "My App" \
  --domain myapp.com \
  --android-package com.myapp.android \
  --ios-bundle-id com.myapp.ios \
  --deep-link-scheme myapp
```

The script substitutes template markers written as a name inside double braces.
The names are `PROJECT_NAME`, `DISPLAY_NAME` (also `APP_NAME`), `DOMAIN`,
`ANDROID_PACKAGE`, `IOS_BUNDLE_ID`, and `DEEP_LINK_SCHEME`. Substitution is literal,
so place display-name markers where the resulting text is valid for the file format.
The positional form in the quick start still works. The domain defaults to
`localhost`. Mobile IDs default to `com.example.<project>` with hyphens and
underscores removed from the project name and an `app` prefix if needed for
a valid identifier. The default scheme uses the project name with underscores
turned into hyphens and an `app-` prefix if it would start with a nonletter.
Display names must omit backslashes, double quotes, dollar signs, and backticks
so they remain literal in the web and mobile env files.

Package names in the lockfiles remain fixed. The script creates missing local
env files from their corresponding `.env.example` files. For the API it
generates a `SECRET_KEY` in `apps/api/.env` and keeps the secret marker in
`apps/api/.env.example`. For the web and optional mobile app it creates
`.env.local`. The mobile file receives the identity values in its existing
configuration variables. Existing local env files are preserved. The script
can be rerun safely and works without `apps/mobile`. Run
`./scripts/test-customize.sh` to exercise both layouts on fixtures.

## Upgrading an existing checkout

For a fresh database, run `make migrate` or `make migrate-compose`. An existing
database created before Alembic already has the three tables in revision `0001`.
Back up that database and verify its tables, constraints and indexes against
[the initial migration](apps/api/alembic/versions/0001_initial_schema.py) before
adopting it. From `apps/api`, with the correct direct database connection configured,
run:

```bash
uv run --locked alembic stamp 0001
uv run --locked alembic upgrade head
uv run --locked alembic check
```

Stamp only a database that already matches revision `0001`. Test the procedure on a
restored copy of your backup first. The Postgres regression test creates the frozen
pre-Alembic schema from `main`, inserts legacy rows, stamps `0001`, upgrades to head
and checks for drift. Revision `0002` adds the idempotency table and builds the
items pagination index concurrently.

Use `postgresql://` or `postgresql+psycopg://` URLs. Earlier Compose projects that
still run a service called `client` can stop that container with
`docker compose down --remove-orphans`, keeping the database volume. Rebuild the API
and web together when updating to the `/v1` paths.

Revision `0003` (auth redesign) changes accounts:

- It refuses to run while two users have emails that differ only by letter case; merge or
  rename those accounts first (the error message includes a query that lists them). It
  builds the case-insensitive unique index concurrently and keeps the old exact-case
  index for one more release. It also refuses duplicate provider links per user; resolve
  those before retrying.
- It drops the Google access/refresh tokens that the removed redirect flow stored. Linked
  Google links on password accounts are marked unconfirmed and require recovery or
  relinking. Configure `GOOGLE_AUTH_ENABLED` and your client IDs, and
  remove `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI` and `FRONTEND_URL` (now
  `WEB_URL`); unknown variables are ignored.
- Legacy Google-only accounts with a non-authoritative address remain unverified on
  Google sign-in. An authoritative matching Google identity or an inbox-proof password
  reset can verify the address; reset retains a passwordless account's Google link.
- Existing password users start unverified and must prove inbox ownership before signing in.
  Their bcrypt hashes are upgraded to argon2id after successful verification or sign-in.
- Old 7-day access tokens stop working: users sign in again. Set `JWT_SECRET_KEY` in
  staging and production before deploying.

## Host development

Host-side commands (`make setup`, `make test`, `make lint`, `make dev`, ...) need:

| Tool                             | Version  | Notes                                                                                                                  |
| -------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| [uv](https://docs.astral.sh/uv/) | 0.13.9   | Enforced by `required-version` in `apps/api/pyproject.toml`. uv installs Python 3.13 if needed.                        |
| Node.js                          | 26 (LTS) | `.nvmrc`                                                                                                               |
| pnpm                             | 12.23.0  | Pinned in `package.json` `packageManager`. Node 25+ has no Corepack, so install it with `npm install -g pnpm@12.23.0`. |

```bash
make setup                      # uv sync --locked + pnpm install --frozen-lockfile
make test                       # starts Compose Postgres and uses boilerplate_test
make dev                        # postgres + api in Docker, web dev server on the host
```

To run the API on the host instead of in Docker:

```bash
docker compose up -d --wait postgres
make migrate
cd apps/api
cp -n .env.example .env
uv run --locked uvicorn app.main:app --reload --no-access-log
```

## Environment variables

**API** ([`.env.example`](apps/api/.env.example))

| Variable                                                                     | Default                                                     | Notes                                                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ENV`                                                                        | `production`                                                | Allowed values are `development`, `test`, `staging`, and `production`. The Compose dev service and `.env.example` set `development`. Other environments use JSON logs and send HSTS.                                                                                                                              |
| `DATABASE_URL`                                                               | Local Compose Postgres in development only                  | Required in test, staging and production. Use the Neon pooled URL for the app.                                                                                                                                                                                                                                    |
| `MIGRATION_DATABASE_URL`                                                     | Falls back to `DATABASE_URL`                                | Use the Neon direct URL for Alembic. Preserve provider connection options such as `sslmode=require`.                                                                                                                                                                                                              |
| `SECRET_KEY`                                                                 | Local development fallback only                             | Server-side HMAC secret (IP hashes, CSRF tokens, rate-limit and audit identifiers). Set a unique secret of at least 32 characters in test, staging and production; the repository's published keys are rejected, even with surrounding whitespace. Rotating it signs web sessions out (their CSRF tokens change). |
| `JWT_SECRET_KEY`                                                             | Derived from `SECRET_KEY` in development and test           | Access-token signing key. Required in staging and production: unique, different from `SECRET_KEY`, and at least 32/48/64 bytes for HS256/HS384/HS512. Rotating it makes clients refresh once.                                                                                                                     |
| `JWT_ALGORITHM`                                                              | `HS256`                                                     | `HS256`, `HS384` or `HS512`.                                                                                                                                                                                                                                                                                      |
| `JWT_ISSUER` / `JWT_AUDIENCE`                                                | `boilerplate-api`                                           | `iss`/`aud` claims, checked on every request.                                                                                                                                                                                                                                                                     |
| `ACCESS_TOKEN_EXPIRE_MINUTES`                                                | `15`                                                        | Access-token lifetime, 1 to 60 minutes.                                                                                                                                                                                                                                                                           |
| `REFRESH_TOKEN_EXPIRE_DAYS`                                                  | `30`                                                        | Idle timeout: each refresh extends the session by this much.                                                                                                                                                                                                                                                      |
| `SESSION_MAX_AGE_DAYS`                                                       | `90`                                                        | Absolute session lifetime; then the user signs in again.                                                                                                                                                                                                                                                          |
| `REAUTHENTICATION_MAX_AGE_MINUTES`                                           | `10`                                                        | How recent a sign-in or re-authentication on the session must be for account deletion, email changes and Google (un)linking.                                                                                                                                                                                      |
| `EMAIL_TOKEN_EXPIRE_HOURS`                                                   | `24`                                                        | Lifetime of email verification and email-change links.                                                                                                                                                                                                                                                            |
| `PASSWORD_RESET_EXPIRE_MINUTES`                                              | `30`                                                        | Lifetime of password reset links.                                                                                                                                                                                                                                                                                 |
| `PASSWORD_BREACH_CHECK`                                                      | `false`                                                     | Reject new passwords found in Have I Been Pwned (k-anonymity range API; fails open).                                                                                                                                                                                                                              |
| `APP_NAME`                                                                   | `Boilerplate App`                                           | Product name in emails.                                                                                                                                                                                                                                                                                           |
| `WEB_URL`                                                                    | `http://localhost:3000`                                     | Base URL of the web app for emailed links. Staging and production require `https`.                                                                                                                                                                                                                                |
| `GOOGLE_AUTH_ENABLED`                                                        | `false`                                                     | Enables `POST /v1/auth/google`. Requires at least one client ID below.                                                                                                                                                                                                                                            |
| `GOOGLE_WEB_CLIENT_ID` / `GOOGLE_ANDROID_CLIENT_ID` / `GOOGLE_IOS_CLIENT_ID` | Unset                                                       | OAuth client IDs (`*.apps.googleusercontent.com`) whose ID tokens are accepted. No client secret is needed.                                                                                                                                                                                                       |
| `EMAIL_BACKEND`                                                              | `console`                                                   | `console` (prints messages and links; development), `smtp`, `resend`, or `memory` (tests). Staging and production require `smtp` or `resend`. Compose uses `smtp` with Mailpit.                                                                                                                                   |
| `EMAIL_FROM`                                                                 | `Boilerplate App <no-reply@localhost>`                      | Sender address.                                                                                                                                                                                                                                                                                                   |
| `SMTP_HOST` / `SMTP_PORT`                                                    | `localhost` / `1025`                                        | SMTP server.                                                                                                                                                                                                                                                                                                      |
| `SMTP_SECURITY`                                                              | `none`                                                      | `none`, `starttls`, or `tls` (implicit TLS).                                                                                                                                                                                                                                                                      |
| `SMTP_USERNAME` / `SMTP_PASSWORD`                                            | Unset                                                       | Set both or neither.                                                                                                                                                                                                                                                                                              |
| `SMTP_ALLOW_INSECURE`                                                        | `false`                                                     | Explicitly allow an unauthenticated plaintext local relay outside development/test. Authenticated SMTP always requires TLS.                                                                                                                                                                                       |
| `SMTP_TIMEOUT_SECONDS`                                                       | `10`                                                        | SMTP connection timeout.                                                                                                                                                                                                                                                                                          |
| `RESEND_API_KEY` / `RESEND_TIMEOUT_SECONDS`                                  | Unset / `10`                                                | Required with `EMAIL_BACKEND=resend`. The job id is sent as the `Idempotency-Key`.                                                                                                                                                                                                                                |
| `WORKER_CONCURRENCY` / `JOB_POLL_INTERVAL_SECONDS`                           | `4` / `2`                                                   | Jobs the worker runs at once, and how often an idle runner polls.                                                                                                                                                                                                                                                 |
| `JOB_TIMEOUT_SECONDS` / `JOB_LOCK_TIMEOUT_SECONDS`                           | `120` / `300`                                               | A handler is cancelled after the first; a claim older than the second is treated as lost and the job runs again. The first must be shorter.                                                                                                                                                                       |
| `PUSH_BACKEND`                                                               | `log`                                                       | `expo` (sends through the Expo Push API), `log` (logs counts only) or `memory` (tests).                                                                                                                                                                                                                           |
| `EXPO_ACCESS_TOKEN` / `EXPO_PUSH_TIMEOUT_SECONDS`                            | Unset / `10`                                                | Optional Expo access token (needed if the Expo project enforces enhanced push security).                                                                                                                                                                                                                          |
| `STORAGE_BACKEND`                                                            | `disabled`                                                  | `s3` (S3, R2, MinIO), `memory` (tests) or `disabled`.                                                                                                                                                                                                                                                             |
| `STORAGE_ENDPOINT_URL` / `STORAGE_BUCKET` / `STORAGE_REGION`                 | Unset / unset / `auto`                                      | S3 endpoint (https outside development/test; path-style), bucket and signing region (`auto` for R2, e.g. `us-east-1` for S3).                                                                                                                                                                                     |
| `STORAGE_ACCESS_KEY_ID` / `STORAGE_SECRET_ACCESS_KEY`                        | Unset                                                       | Required with `STORAGE_BACKEND=s3`.                                                                                                                                                                                                                                                                               |
| `STORAGE_MAX_UPLOAD_BYTES` / `STORAGE_URL_EXPIRE_SECONDS`                    | `10485760` / `600`                                          | Largest allowed upload, and how long presigned URLs live.                                                                                                                                                                                                                                                         |
| `STORAGE_ALLOWED_CONTENT_TYPES`                                              | `["image/jpeg","image/png","image/webp","application/pdf"]` | JSON array of exact content types.                                                                                                                                                                                                                                                                                |
| `MIN_SUPPORTED_APP_VERSION` / `LATEST_APP_VERSION`                           | `0.0.0` / `1.0.0`                                           | Returned by `GET /v1/meta`. Mobile clients below the minimum get `426 app_update_required`.                                                                                                                                                                                                                       |
| `SENTRY_DSN` / `SENTRY_RELEASE` / `SENTRY_TRACES_SAMPLE_RATE`                | Unset / `api@<version>` / `0`                               | Sentry for the API and worker; nothing is initialised without a DSN.                                                                                                                                                                                                                                              |
| `RATE_LIMIT_BACKEND`                                                         | `postgres`                                                  | `postgres`, or `memory` (per process; development and test only).                                                                                                                                                                                                                                                 |
| `CORS_ORIGINS`                                                               | `["http://localhost:3000"]`                                 | JSON array of explicit `http://` or `https://` origins with an optional port. Origins are lowercased and default ports (`:443`, `:80`) are dropped, as browsers send them. Omit paths, even a trailing slash. Also the allowlist for the `Origin` check on web sign-in and cookie refresh.                        |
| `TRUSTED_HOSTS`                                                              | `["localhost","127.0.0.1","[::1]"]`                         | JSON array of permitted hosts without ports. Staging and production reject `*`. Probes accept any Host.                                                                                                                                                                                                           |
| `MAX_REQUEST_BODY_BYTES`                                                     | `1048576`                                                   | Maximum HTTP body size in bytes, including chunked requests.                                                                                                                                                                                                                                                      |
| `HEALTHCHECK_URL`                                                            | `http://127.0.0.1:8000/health`                              | Optional override for the container probe, which reads the process environment.                                                                                                                                                                                                                                   |

Behind a reverse proxy, run uvicorn with `--forwarded-allow-ips` set to the proxy's
addresses so per-IP rate limits and IP hashes see the client address, not the proxy's.

Run the Alembic upgrade with the direct connection before starting new API
instances. `/ready` returns 503 if the DB is unreachable, unmigrated or behind the
image. Unknown revisions are treated as newer; the API logs their IDs once per distinct
set per process. Migration 0003 requires a coordinated cutover: stop old API instances,
apply the migration, then start the new release. It drops columns old instances read and
invalidates old access tokens. Resolve duplicate case-insensitive emails and duplicate
provider links before migrating; the preflight error identifies the required cleanup.
See [ADR 0004](docs/adr/0004-async-postgres.md).

**Web** ([`.env.example`](apps/web/.env.example))

| Variable                           | Default                                                                   | Notes                                                                                                                                                                                                                                                                                                            |
| ---------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_URL`              | `http://localhost:8000`                                                   | Inlined at **build** time. Must be reachable from the browser. For the Docker image it is a build arg (`--build-arg NEXT_PUBLIC_API_URL=...`; Compose reads it from your shell or a root `.env`); env files are not copied into the image.                                                                       |
| `WEB_LEGAL_APP_NAME`               | `Full-stack starter` in the shell and `[App name]` in the legal templates | Name shown in the header, landing page, page metadata, and public policy and deletion templates.                                                                                                                                                                                                                 |
| `WEB_LEGAL_DOMAIN`                 | `[Site domain]` placeholder                                               | Domain shown in the privacy and terms templates.                                                                                                                                                                                                                                                                 |
| `WEB_SUPPORT_EMAIL`                | Unset                                                                     | Monitored mailbox for deletion requests sent from `/account-deletion`.                                                                                                                                                                                                                                           |
| `ANDROID_PACKAGE_NAME`             | Unset                                                                     | Android application ID, for example `com.example.app`.                                                                                                                                                                                                                                                           |
| `ANDROID_SHA256_CERT_FINGERPRINTS` | Unset                                                                     | Comma-separated, colon-delimited SHA-256 signing certificate fingerprints. Include the Play App Signing certificate for Play builds.                                                                                                                                                                             |
| `IOS_TEAM_ID`                      | Unset                                                                     | 10-character Apple Developer Team ID.                                                                                                                                                                                                                                                                            |
| `IOS_BUNDLE_ID`                    | Unset                                                                     | iOS bundle identifier, for example `com.example.app`.                                                                                                                                                                                                                                                            |
| `IOS_APPLINK_PATHS`                | `/app/*`                                                                  | Comma-separated URL paths beginning with `/`. Supports `*` for any number of characters and `?` for one character. Include the email-verification, password-reset and invite paths that the mobile app handles. The root path and any pattern matching `/privacy`, `/terms` or `/account-deletion` are rejected. |

Host development and `make up` both read the legal, support and association
settings from the optional `apps/web/.env.local` at **runtime**. After changing
that file, run `make up` again to apply the values in Compose. When running the
standalone image directly, pass the variables to the container, for example with
`docker run -e WEB_SUPPORT_EMAIL=support@example.com …`.

### Public pages and mobile links

- `scripts/customize.sh PROJECT_NAME "App Name" DOMAIN` fills the legal app and domain
  values in the web env example. It copies that example to `apps/web/.env.local` when the
  local file is absent. The script rejects backslashes, double quotes, dollar signs,
  backticks, and line breaks in the display name so both dotenv readers interpret it
  literally. Run `make up` and visit `/privacy` to see the configured values.
  Before publishing, complete the privacy and terms templates and the account deletion
  template, including the in-app workflow, the data deleted or retained, and retention
  periods. Set `WEB_SUPPORT_EMAIL` to a monitored mailbox. At startup, the web server
  logs a warning for a missing or invalid mailbox and any invalid association setting.
- The Android and Apple association URLs each return `application/json` from the
  slashless path and return 404 until their corresponding settings are valid. Successful
  association documents are cacheable for one hour. Verify both URLs return 200 over
  HTTPS without redirects on the public domain.

**Mobile** (`apps/mobile/.env` for local Expo CLI runs; template with comments in
`apps/mobile/.env.example`). Read by `app.config.ts` and validated there: an invalid
value fails `expo start`, `expo-doctor`, EAS Build and EAS Update. Error messages name
the variable but never print its value. Every value is embedded in the app and readable
by its users, so none of them may be secret. EAS CLI does **not** read `.env`; see
[EAS](#eas-builds-and-updates).

| Variable                        | Default                                                  | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| ------------------------------- | -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `APP_VARIANT`                   | `development` for local Expo CLI; **required** under EAS | `development` / `preview` / `production`. Under EAS CLI or on an EAS Build worker there is no default, and on a worker it must match a profile named after a variant. Non-production variants get `.dev` / `.preview` id suffixes, `-dev` / `-preview` scheme suffixes and a name suffix, so they install side by side. Also selects the runtime version (`1.0.0-<variant>`).                                                                                                                                                                                           |
| `API_URL`                       | `http://localhost:8000` (development only)               | Required and `https://` for `preview` and `production`. No credentials, query string or fragment. Exposed to the app as `extra.apiUrl`; not used yet (no API calls).                                                                                                                                                                                                                                                                                                                                                                                                    |
| `APP_NAME` / `APP_SLUG`         | `Boilerplate` / `fullstack-boilerplate`                  | Display name; EAS project slug.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `ANDROID_PACKAGE`               | `com.example.boilerplate`; **required** for production   | Java package rules (letters, digits, `_`). Production rejects the `com.example` placeholder (Google Play does too). It can't change after the first Play release.                                                                                                                                                                                                                                                                                                                                                                                                       |
| `IOS_BUNDLE_ID`                 | `com.example.boilerplate`; **required** for production   | Letters, digits, `-` (no `_`). Same production rules.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `APP_SCHEME`                    | `boilerplate`                                            | Deep-link scheme (before the variant suffix).                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `APP_DOMAIN`                    | unset                                                    | Bare host for App Links / universal links, e.g. `app.example.com`. Has no effect without `APP_LINK_PATHS`. Use different hosts for preview and production.                                                                                                                                                                                                                                                                                                                                                                                                              |
| `APP_LINK_PATHS`                | unset                                                    | Explicit opt-in: comma-separated paths the app claims on `APP_DOMAIN`. `/verify-email` matches exactly, `/invite/` matches whole segments below it. No wildcards; `/privacy`, `/terms`, `/account-deletion` and `/.well-known` are always refused. Adds the Android `autoVerify` intent filter and the iOS `applinks:` domain. The web app's `IOS_APPLINK_PATHS` (AASA globs) must cover the same paths: `/verify-email` there for `/verify-email` here, `/invite/*` for `/invite/`. Its `ANDROID_PACKAGE_NAME` is the installed package, including the variant suffix. |
| `EAS_PROJECT_ID` / `EXPO_OWNER` | unset                                                    | From `eas init`. The project id also sets the EAS Update URL.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `SENTRY_DSN`                    | unset                                                    | Read into `extra.sentryDsn`; Sentry is not wired up yet.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

## Common commands

```bash
make help                      # list all targets
make setup                     # install locked Python + JS dependencies
make hooks                     # install the Git pre-commit hook
make up / make down            # start / stop the Docker stack
make ps / make logs            # status (including health) / follow logs
make dev                       # api in Docker + web dev server with hot reload
make test                      # API tests (pytest)
make lint                      # ruff check + ESLint (web, mobile)
make typecheck                 # mypy + tsc (web, mobile)
make fmt / make fmt-check      # ruff format + Prettier (write / check)
make build-web                 # production build of the web app
make mobile                    # Expo dev server for apps/mobile
make test-mobile               # mobile unit tests (Jest)
make doctor-mobile             # expo-doctor for apps/mobile
make migrate                   # alembic upgrade head from the host
make migrate-compose           # alembic upgrade head in a one-off Compose container
make migration name=add_column # autogenerate a migration
make db-shell                  # psql into the dev database
make fresh                     # wipe the DB volume, rebuild, start
make smoke                     # packaged containers, health and production API/web checks
```

## Security checks

Security checks run on PRs, pushes to `main`, and Mondays at 06:23 UTC.
The jobs use SHA-pinned Actions and read-only contents access.
[`security.yml`](.github/workflows/security.yml) · [ADR 0011](docs/adr/0011-security-checks.md)

| Check                    | Coverage and failure condition                                                                                                                                                                 |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gitleaks                 | Scans PR commits from the base SHA to the head SHA. On `main` pushes and the weekly run, scans the full fetched history across branches and tags. Reports matches with secret values redacted. |
| GitHub Dependency Review | Runs on PRs and fails on newly introduced known vulnerabilities at low severity or higher in the dependency graph. Requires the repository's **Dependency graph** setting.                     |
| pip-audit                | Exports exact versions and hashes from `apps/api/uv.lock`, including development groups. Fails on known vulnerabilities reported for the export by the advisory service.                       |
| pnpm audit               | Audits the workspace lockfile's production dependencies and fails on high or critical advisories.                                                                                              |

Dependency Review needs the repository's dependency graph. Enable it in
**Settings → Advanced Security → Dependency Graph**, then rerun the job. If the
dependency graph API returns 403 or 404, the job reports a warning and skips
the review. Other API errors still fail the job.

To scan history locally with Gitleaks 8.30.1 installed, fetch `origin` and run
`gitleaks git --redact --log-opts="--diff-merges=first-parent --remotes=origin --tags HEAD" .`.
For a confirmed credential exposure, revoke or rotate the credential and
remove it from current code. Review the affected commit range before deciding
how to clean up published history.

## Pre-commit

Install the repository's pinned tools (uv and pnpm are listed under Host
development), then enable the hook from the repository root.

```bash
make setup
uv tool install pre-commit==4.7.0
make hooks
pre-commit run --all-files
```

Ruff check and format use the API lockfile, as does mypy. Prettier formats staged
files in the JS workspaces, and ESLint runs workspace lint scripts through
Turborepo. The hooks also check YAML, JSON, large files and private keys, fix
trailing whitespace and missing final newlines, and scan staged changes with
Gitleaks. Pre-commit provisions the Gitleaks hook's Go environment if needed.
Review and re-stage any fixes before committing.

CI runs `pre-commit run --all-files` on PRs and pushes to `main`. Gitleaks'
hook reads the Git index diff, so the Security workflow scans committed changes
in CI. [`pre-commit.yml`](.github/workflows/pre-commit.yml)

## Authentication

Design records: [ADR 0008](docs/adr/0008-auth-tokens-and-sessions.md) (tokens, sessions,
web and mobile transport), [ADR 0009](docs/adr/0009-google-id-token-sign-in.md) (Google
sign-in and account linking) and [ADR 0010](docs/adr/0010-rate-limits-email-audit.md)
(rate limits, email delivery, audit log, enumeration resistance).

| Endpoint                                | Purpose                                                                                     |
| --------------------------------------- | ------------------------------------------------------------------------------------------- |
| `POST /v1/auth/register`                | Create an account and email a verification link. Always `202` with the same body.           |
| `POST /v1/auth/login`                   | Email and password sign-in. Returns tokens (below).                                         |
| `POST /v1/auth/google`                  | Sign in or sign up with a Google ID token `{id_token}`.                                     |
| `POST /v1/auth/refresh`                 | Exchange a refresh token for new tokens (rotation).                                         |
| `POST /v1/auth/logout`                  | Revoke the current session.                                                                 |
| `POST /v1/auth/verify-email`            | Confirm an email address with the emailed token.                                            |
| `POST /v1/auth/verify-email/resend`     | Request a new verification link by email.                                                   |
| `POST /v1/auth/password/forgot`         | Email a reset link. Always `202` with the same body.                                        |
| `POST /v1/auth/password/reset`          | Set a new password with the emailed token; signs out every session.                         |
| `POST /v1/auth/email/confirm`           | Confirm a new email address with the emailed token.                                         |
| `POST /v1/auth/reauthenticate`          | Confirm the user with `{password}` or a Google `{id_token}` issued in the last few minutes. |
| `POST`/`DELETE /v1/auth/google/link`    | Link or unlink Google for the signed-in user (recent re-authentication required).           |
| `GET /v1/auth/sessions`                 | The user's active sessions (devices), the current one marked.                               |
| `DELETE /v1/auth/sessions/{session_id}` | Revoke one session.                                                                         |
| `POST /v1/auth/sessions/revoke-others`  | Revoke every session except the current one.                                                |
| `GET`/`PATCH /v1/me`                    | Read or update the profile.                                                                 |
| `POST /v1/me/password`                  | Change the password (current password required); signs out other sessions.                  |
| `POST /v1/me/email`                     | Request an email change; the address changes once the new one is confirmed.                 |
| `DELETE /v1/me`                         | Delete the account (recent re-authentication required).                                     |

**Platform endpoints.**

| Endpoint             | Purpose                                                                                                                             |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `GET /v1/meta`       | `{min_supported_app_version, latest_app_version}`; no authentication, never version-gated.                                          |
| `POST /v1/devices`   | Register or refresh the caller's Expo push token `{expo_push_token, platform, app_version}`. An existing token moves to the caller. |
| `DELETE /v1/devices` | Remove a token `{expo_push_token}` owned by the caller (call it on sign-out). Always `204`.                                         |

**Tokens.** Access tokens are HMAC-signed JWTs (HS256 by default; `typ: at+jwt`; `iss`,
`aud`, `sub`, `sid`, `iat`, `exp`, `jti`) valid for 15 minutes, with 30 seconds of
tolerance for clock differences between API instances. Every request also checks that the session
(`sid`) is still active, so signing out or revoking a session takes effect immediately.
Refresh tokens are random 256-bit strings stored only as SHA-256 digests. Each one works
once: refreshing returns a new one. Presenting a refresh token that was already used
revokes the whole session (its token family) and is recorded as `refresh_token_reused`,
so clients must not refresh concurrently with the same token. Sessions expire after 30
idle days and at most 90 days after sign-in.

**Web clients** send `X-Platform: web` when signing in. The refresh token is then set as
an `HttpOnly`, `Secure` (except in development), `SameSite=Strict` cookie limited to
`/v1/auth/refresh`, and the response body carries a CSRF token instead. To refresh, send
no body, the cookie and an `X-CSRF-Token` header; the request's `Origin` must be in
`CORS_ORIGINS`. The CSRF token is bound to the session (an HMAC of its ID) and matched
against a second cookie. The cookie is host-only on the API's host, so the web app and
API must be same-site (for example `app.example.com` and `api.example.com`). The
current web app keeps the access token in memory and the CSRF token in `localStorage`.

**Mobile and other clients** (any other `X-Platform` value, or none) get `refresh_token`
in the response body and send `{"refresh_token": ...}` to `/v1/auth/refresh`. They should
store it in secure storage.

**Passwords** are 12 to 128 characters for new passwords, hashed with argon2id
(19 MiB, 2 iterations, 1 lane). Hashes from the previous release (bcrypt) are verified
and upgraded at sign-in. Submitted passwords are capped at 1,024 characters; users
with longer legacy passwords must use password reset. The breached-password check is
optional and off by default.

**Email verification.** Password sign-in requires a verified address. Registration
sends a link tied to the chosen password; the recipient enters that password to verify.
Up to five pending links remain valid, each bound to its own password and chosen name;
issuing another evicts the oldest. A successful claim invalidates the rest.
Claiming an unverified account revokes earlier sessions and removes untrusted links and
tokens. Links put tokens in the URL fragment (`#token=`), so servers do not receive them.

**Google.** `POST /v1/auth/google` verifies Google ID tokens. Automatic linking and
mailbox verification require an authoritative Google address (Gmail or a matching
Workspace hosted domain); third-party addresses require local verification or explicit
linking from an authenticated account. Legacy links on password accounts require recovery
or explicit relinking. Unlinking revokes sessions established through that identity and
prevents automatic relinking.

**Account deletion.** `DELETE /v1/me` needs a sign-in or `POST /v1/auth/reauthenticate`
on the same session within `REAUTHENTICATION_MAX_AGE_MINUTES`. It runs the registered
deletion hooks (a module can block deletion with `409 account_deletion_blocked` or clean
up data it owns; see `app/modules/auth/deletion.py`), deletes the user row and,
through foreign-key cascades, sessions, refresh tokens, linked identities, emailed
tokens, idempotency records and items, then emails a confirmation. Audit events are kept
with the user ID but without email addresses or names.

**Rate limits** return `429` with `Retry-After` and the error envelope (`rate_limited`,
`details.retry_after`). Identifiers are stored as HMAC digests.

| Action                                | Per IP      | Per account                                                                        |
| ------------------------------------- | ----------- | ---------------------------------------------------------------------------------- |
| Sign-in                               | 50 / 15 min | 20 / 15 min, plus a lockout after 5 consecutive failures: 30 s, doubling to 15 min |
| Registration                          | 10 / hour   | 3 / hour per email                                                                 |
| Google sign-in                        | 50 / 15 min | 20 / 15 min per Google account                                                     |
| Password reset request                | 10 / hour   | 3 / hour per email                                                                 |
| Verification resend                   | 10 / hour   | 3 / hour                                                                           |
| Email change request                  |             | 3 / hour                                                                           |
| Re-authentication and password change |             | 10 / 15 min, plus the failure lockout                                              |

**Enumeration.** Registration and reset requests answer the same way for every address,
and sign-in failures share one error (accounts without a password are checked against a
dummy hash). One limit remains: someone who registers an address and then signs in with
the password they chose learns that the address had no account. That needs a new
account per probe, is rate limited, and emails the address's owner.

**Audit log.** `audit_events` records sign-in success and failure, sign-out, refresh
token reuse, session revocation, re-authentication, registration, email verification,
password change, reset request and reset, email change request and change, Google link
and unlink, and account deletion, with the user and session IDs, an IP digest and a
coarse client label. Failed sign-ins store an email digest, not the address.

## API contracts

`GET /v1/items?limit=25` returns `{"items": [...], "next_cursor": "..."}`.
Pass the returned cursor as `cursor` on the next request. The maximum page size
is 100 and a null cursor marks the last page.

`POST /v1/items`, `PATCH/DELETE /v1/items/{item_id}` and `PATCH /v1/me` accept an
optional `Idempotency-Key` of up to 128 visible ASCII characters. Retry with the
same user, key, method, path, query string, media type and identical body bytes.
`Content-Type` parameters such as `charset` are ignored. Preserve the serialized JSON,
including whitespace and property order. A retry replays the committed status and
response body for up to 24 hours. Reusing the key for a different request returns 422. An overlapping request with the same user and key returns 409. Failed transactions leave the key available for retry.
Expired records can be reused. Periodic cleanup is part of the future jobs phase.

Errors return `{"error": {"code": "...", "message": "...", "details": {}}}`.
Validation errors list invalid field locations and error types. The API accepts a
short ASCII `X-Request-Id` tracing token or generates one, and returns it on responses.

## Testing

Run the web checks from the repository root. Playwright serves the existing Next.js
standalone build on port 3308. It injects the app name, domain, support mailbox and
mobile association settings when the server starts.

```bash
pnpm --filter web test
pnpm turbo run build
pnpm --filter web exec playwright install chromium
pnpm --filter web test:e2e
```

On Linux, use `playwright install --with-deps chromium` to install the system libraries
as well. The suite checks public navigation, theme persistence, form feedback, security
headers, and the association URLs. It also checks that values supplied at server start
appear in the public pages. `make smoke` repeats the HTTP checks against the Docker image
for both association URLs, response headers, and the runtime values on `/privacy` and
`/account-deletion`.

`make test` creates and uses the dedicated `boilerplate_test` database on Compose
Postgres. To use another dedicated Postgres database, run
`make test TEST_DATABASE_URL=postgresql://user:password@host/dbname`. With pytest
directly, run from `apps/api` with `ENV=test`, `DATABASE_URL` set to that database,
and a throwaway `SECRET_KEY` (for example, `export SECRET_KEY="$(openssl rand -hex 32)"`).
For a targeted run, use `uv run --locked pytest --no-cov tests/test_settings.py` to
skip the suite-wide coverage gate. The test user needs
permission to create schemas. Each database test applies Alembic to its own schema
and drops the schema afterward. HTTP tests use httpx's ASGI transport and real
request transactions. Tests use the in-memory email and rate-limit backends and a fake
Google verifier; the Postgres rate limiter and the real Google verifier (with locally
signed tokens and a mocked certificate endpoint) have their own tests. CI applies
migrations to its Postgres 16 service, runs `alembic check` for schema drift and runs
the same suite. Plain pytest, `make test` and CI share the 96.0% branch-aware coverage
gate in `apps/api/pyproject.toml`, with greenlet and thread tracing enabled.

Mobile unit tests (Jest + React Native Testing Library, no device needed):
`make test-mobile`. They cover the design tokens (including WCAG AA contrast), the secure
token storage wrapper, the persisted query cache, network status and the offline banner,
the app config validation, the Android manifest that `expo prebuild` would generate, and
routing and flow tests that render the real `src/app` tree against a fake API (sign-up,
sign-in, email-link screens, items list and pull-to-refresh, an offline create replayed on
reconnect, the 426 screen), plus unit tests for token refresh (single flight, session
binding, transient failures), the offline queue and the push route allowlist.

## Mobile

`apps/mobile` is an Expo SDK 58 app on the generated API client
([ADR 0012](docs/adr/0012-api-client.md)). Design notes for sessions and the offline
queue are in [ADR 0013](docs/adr/0013-mobile-session-and-offline-queue.md).

### Features

- **Auth.** Sign in, sign up (then a "check your email" screen: the API blocks sign-in
  until the email is verified), forgot password. The email links open
  `/auth/verify-email?token=` (asks for the password chosen at sign-up, which the API
  requires with the token) and `/auth/reset-password?token=`. Sessions, profile (name,
  change password) and account deletion (re-authenticates first) are in Settings.
  The app does not change the email address or link/unlink Google yet.
- **Token refresh.** A 401 triggers one refresh for all concurrent requests. The refresh
  stays bound to the session the request was sent as: if the user signed out or switched
  account meanwhile, the pending request is not replayed. Requests send `X-App-Version`,
  `X-Platform`, `X-Workspace-Id` (the active workspace) and, on writes, `Idempotency-Key`.
  A `426` replaces the app with a "Please update" screen.
- **Google sign-in** uses `@react-native-google-signin/google-signin` and sends the ID token
  to `POST /v1/auth/google`. It needs a **development or production build** (not Expo Go) and
  `GOOGLE_WEB_CLIENT_ID` (+ `GOOGLE_IOS_CLIENT_ID` for iOS); the button is hidden when either
  is missing. The web client id must be one of the API's configured Google client ids. Android
  also needs your signing SHA-1 registered on the Android OAuth client in Google Cloud. None of
  this has been run against real Google here.
- **Items.** List with pull-to-refresh, create, edit, delete. Creates and edits go through a
  persisted queue (see ADR 0013) and show at once as "Waiting to sync"; they are replayed
  with their original idempotency keys when the connection returns.
- **Workspaces, members, invitations** (provisional). The screens exist (switch, create,
  members, invite link with share sheet and QR code, accept via `/invite/<token>`), but
  they call endpoints that are not in the generated client yet:
  `/v1/workspaces`, `/v1/workspaces/{id}/members`, `/v1/workspaces/{id}/invitations`,
  `/v1/invitations/accept`. The request and response shapes are an assumption taken from the
  spec and live in `src/features/workspaces/workspace-api.ts`; replace them with typed client
  calls after phase 5 lands. Until then they are untested against a real server.
- **Biometric lock** (Settings): locks at launch and after 30 s in the background; turning it
  on requires a successful biometric check. It is a UI gate, not encryption.
- **Push.** A dismissible card on the Items tab (not at launch) asks for permission; once
  granted, the Expo push token is registered with `POST /v1/devices` on each start and removed
  at sign-out. Tapping a notification follows `data.url` only if it is an allowed in-app route.
  Tokens need a physical device, an EAS project id (`EAS_PROJECT_ID`) and, on Android, FCM
  credentials; none of that was exercised here.
- **Deep links.** The scheme works everywhere. For Android App Links set `APP_DOMAIN` and
  `APP_LINK_PATHS=/auth/verify-email,/auth/reset-password,/invite/` (exact and prefix paths,
  as the API's email links and the invite links use them). `/privacy`, `/terms` and
  `/account-deletion` stay refused.

### Running it

You need an Android emulator (Android Studio), an iOS simulator (Xcode, macOS only) or a
physical device.

```bash
make setup                                    # once: installs all JS dependencies
cp apps/mobile/.env.example apps/mobile/.env  # optional; set API_URL for your target
make mobile                                   # = pnpm --filter mobile start
```

Because `expo-dev-client` is installed, `expo start` serves a development build by
default. To use Expo Go instead, press `s` to switch, then `a` (Android emulator) or `i`
(iOS simulator), or scan the QR code with Expo Go on a device on the same network. `API_URL` must be reachable from the
device: `http://10.0.2.2:8000` from the Android emulator, `http://localhost:8000` from the
iOS simulator, `http://<your LAN IP>:8000` from a physical device.

**Expo Go vs development builds.** Expo Go only contains the native modules bundled with
the Expo SDK. Every native dependency the app uses today is an Expo SDK module or one
whose version `expo install` resolves for SDK 58. Later features (for example native
Google Sign-In) need modules Expo Go doesn't have. From then on, use a development build,
which is your app with `expo-dev-client`:

```bash
cd apps/mobile
pnpm exec expo run:android   # local build; needs the Android SDK. Or: expo run:ios
# or in the cloud: pnpm exec eas build --profile development --platform android (see EAS below)
```

`expo run:*` generates `android/` and `ios/` (Continuous Native Generation). They are
git-ignored. Configure native behaviour in `app.config.ts` and config plugins, not by
editing those folders.

### Layout

```
apps/mobile/
  app.config.ts            env-driven Expo config (validated; see the env table above)
  eas.json                 EAS Build profiles and EAS Update channels
  src/app/                 routes (Expo Router)
    _layout.tsx            providers, session gate, app lock, protected root stack
    index.tsx              redirects to sign-in, the app, or a pending invitation
    (auth)/                sign-in, sign-up, check-email, forgot-password
    auth/                  verify-email, reset-password (email deep links)
    invite/[token].tsx     accept an invitation (deep link)
    (app)/(tabs)/          items, workspaces, settings (bottom tabs)
    (app)/                 item/new, item/[id], members, invite-share, workspace-new,
                           profile, sessions, delete-account (pushed over the tabs)
  src/features/            auth, items (queue), push, lock, workspaces
  src/components/          Screen, KeyboardAvoidingForm, TextField, Button, NetworkBanner
  src/theme/               design tokens + useTheme (ADR 0006)
  src/lib/                 runtime env, query client, network status, token storage,
                           session store, API wiring, mutation queue
```

### What the foundation provides

- **Safe areas and edge-to-edge.** Expo SDK 54+ apps are always edge-to-edge on Android
  (and Android 15+ enforces it for apps targeting API 35), so content draws behind the
  system bars. `Screen` pads with safe-area insets per edge; headers and the tab bar pad
  their own edges. The status bar icons follow the theme.
- **Android back button.** In the tabs, back returns to the first tab, then leaves the
  app (`backBehavior="initialRoute"`). Signing in uses `router.replace`, so
  back from the tabs doesn't return to sign-in. On sign-up, leaving with unsaved input
  (hardware back, header back, iOS swipe) asks for confirmation (`usePreventRemove`);
  "Discard" clears the input and completes the navigation. `(auth)` is anchored on
  sign-in, so opening `/sign-up` directly still has sign-in underneath it. Android's
  predictive back gesture is off (`predictiveBackGestureEnabled: false`).
- **Keyboard.** Android windows no longer resize for the keyboard under edge-to-edge,
  so `KeyboardAvoidingForm` pads itself by however much the keyboard overlaps it. It
  measures its own bottom edge in window coordinates against the keyboard's top edge,
  so headers and the offline banner need no offset, and it recomputes on every keyboard
  event and every layout change (e.g. the banner appearing while the keyboard is open).
- **Accessibility.** Inputs are labelled, buttons have roles and disabled state, screen
  titles are headers, tabs have accessibility labels, buttons and inputs are at least
  48 dp tall. In light and dark, the color pairs the components draw together meet WCAG
  AA: 4.5:1 for text and 3:1 for the outlines and fills that identify controls (tested).
- **Data layer scaffold.** TanStack Query with a cache persisted to AsyncStorage (24 h
  max age; discarded when the app version changes). AsyncStorage is not encrypted, so
  persistence is opt-in: only successful queries with `meta: { persist: true }` are
  written, and mutations (whose variables can hold passwords) never are. The cache is
  scoped per account: `AppProviders` takes a `cacheScope` (account id, or signed out),
  each scope has its own storage entry, and other scopes' entries are deleted on
  startup. Sign-out calls `useClearQueryCache()`: it stops the scope's writes
  (including throttled writes still queued), waits for writes in flight, then clears
  memory and deletes the entry, so nothing can recreate it. Queries pause offline and
  resume on reconnect; returning to the foreground refetches and re-checks
  connectivity.
- **Offline banner.** Shown when NetInfo reports no connection or no internet access.
  It is an accessibility alert and a polite live region (announced on Android when it
  appears), and it takes over the top safe-area inset while visible.
- **Token storage** (`src/lib/token-storage.ts`): typed wrapper over `expo-secure-store`
  (Keychain / Keystore, `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`). The session (access +
  refresh token) is one entry, so a failed write never leaves a mixed pair. The
  session store (`src/lib/session.ts`) is the only writer.
- **Android release hardening.** Android Auto Backup is off (`allowBackup: false`), and
  permissions the app doesn't use (`SYSTEM_ALERT_WINDOW`, `VIBRATE`, legacy external
  storage) are removed from the merged manifest (`blockedPermissions`). A test checks the
  manifest that `expo prebuild` would generate for a production config.
- **API headers** (`src/lib/client-headers.ts`): builds `X-App-Version` / `X-Platform`
  values for the API's minimum-version check. Not sent yet.

### EAS builds and updates

| Profile       | Purpose                                                       | Output                                                               | EAS environment | Update channel                                   |
| ------------- | ------------------------------------------------------------- | -------------------------------------------------------------------- | --------------- | ------------------------------------------------ |
| `development` | Development client (`expo-dev-client`), internal distribution | APK (Android)                                                        | `development`   | none: a dev client loads JS from your dev server |
| `preview`     | Internal testing build                                        | APK, internal distribution                                           | `preview`       | `preview`                                        |
| `production`  | Store build                                                   | AAB (Android); `versionCode` / `buildNumber` auto-incremented by EAS | `production`    | `production`                                     |

- Build numbers are managed by EAS (`cli.appVersionSource: "remote"`). The user-facing
  version is `APP_VERSION` in `app.config.ts`.
- **Runtime version per variant:** `1.0.0-development`, `1.0.0-preview`,
  `1.0.0-production`. EAS Update only delivers an update to builds with the same
  runtime version, so an update exported with the wrong variant can never reach preview
  or production binaries.
- `eas.json` pins EAS's Node (26.13.1) and pnpm (12.23.0) to match the repo, and
  `cli.version` to the root `eas-cli` devDependency (27.10.0). Run EAS CLI as
  `pnpm exec eas` from `apps/mobile`, not a global or `@latest` install.

**How EAS reads the config** (checked against `eas-cli` 27.10.0). EAS CLI evaluates
`app.config.ts` on your machine with `.env` loading turned off, using only your shell's
environment, and it does so _before_ it fetches EAS environment variables. Build workers
then evaluate it again with the profile's `env` from `eas.json` plus the EAS environment
variables of the profile's `environment`; `eas update --environment <env>` uses that
environment's variables. So:

- EAS environment variables are the source of truth for builds and updates. Each
  environment must define `APP_VARIANT` (equal to its name) and the values below.
  `eas update` does not read `eas.json` profiles.
- Your shell needs the same values exported for the local evaluation (a preflight).
  Under EAS, `APP_VARIANT` has no default, and `preview`/`production` refuse to
  evaluate without `API_URL`; production also needs real `ANDROID_PACKAGE` and
  `IOS_BUNDLE_ID`.
- `eas init` can't edit a dynamic `app.config.ts`: it creates the project, prints the
  project id with a warning, and **exits non-zero** (eas-cli 27.10.0 throws after the
  warning). Export the id as `EAS_PROJECT_ID`; `app.config.ts` then reports it, and
  `eas init --id "$EAS_PROJECT_ID"` confirms the link and exits 0.

First-time setup (needs an Expo account; none of this has been run for this repo):

```bash
cd apps/mobile
pnpm exec eas login
export APP_VARIANT=development          # preflight: EAS CLI reads only your shell
pnpm exec eas init                      # creates the project, prints its id, exits non-zero
export EAS_PROJECT_ID=<printed id> EXPO_OWNER=<your Expo account>
pnpm exec eas init --id "$EAS_PROJECT_ID"   # "Project already linked", exits 0

# Source of truth for build workers and EAS Update:
for env in development preview production; do
  pnpm exec eas env:set --environment "$env" --name APP_VARIANT --value "$env" --visibility plaintext
  pnpm exec eas env:set --environment "$env" --name EAS_PROJECT_ID --value "$EAS_PROJECT_ID" --visibility plaintext
  pnpm exec eas env:set --environment "$env" --name EXPO_OWNER --value "$EXPO_OWNER" --visibility plaintext
done
pnpm exec eas env:set --environment preview --name API_URL --value https://api-preview.example.com --visibility plaintext
# production: API_URL, ANDROID_PACKAGE, IOS_BUNDLE_ID (and APP_DOMAIN / APP_LINK_PATHS if used)
```

**Builds** (keep `EAS_PROJECT_ID` / `EXPO_OWNER` exported, e.g. via your shell profile or
direnv, and export the target's values for the local evaluation). The worker builds from
the profile's `APP_VARIANT` and EAS environment, and refuses a variant that doesn't match
the profile:

```bash
export APP_VARIANT=preview API_URL=https://api-preview.example.com
pnpm exec eas build --profile preview --platform android
```

**Updates: use the release script, not `eas update` directly.** EAS overlays the hosted
environment on your shell, so a value missing from the hosted environment silently
falls back to the shell (for example a stale `APP_VARIANT=production` with
`--environment development`). `pnpm release:update <preview|production>` derives the
channel, the EAS environment and the variant from its one argument. Before publishing it
pulls the hosted environment (`eas env:pull`, into a temp dir that is deleted again) and
refuses to publish unless that environment defines `APP_VARIANT` equal to the target, an
`API_URL` valid for the variant (https), the same `EAS_PROJECT_ID` as your shell, and
(production) real app ids. It then runs `eas update` with your shell's app settings
removed:

```bash
pnpm release:update preview --message "Fix the settings screen"
pnpm release:update production --message "..."
```

Updates also carry the variant's runtime version (`1.0.0-<variant>`), so even an update
published by hand with the wrong variant is ignored by the other variants' builds.

## Adding a domain entity

Use `app/modules/items` as the template. Add the model, migration, repository,
service, input/output schemas, router and tests under `apps/api/tests/`. Register the
router in `app/main.py`. [CLAUDE_CONTEXT.md](CLAUDE_CONTEXT.md) describes the conventions.

## Troubleshooting

**`Illegal instruction` (exit code 132) when running the API in Docker on an Apple M4
Mac.** We have seen OpenSSL, as loaded by the Python `cryptography` package, crash inside
Linux containers on an M4 Pro (Docker Desktop, engine 27.5). Setting `OPENSSL_armcap=0`
in the container environment avoids it (verified). Set it on the `api` service in a
local Compose override. For `make smoke`, also pass `OPENSSL_armcap=0` in the host
environment so the smoke script applies it to the standalone missing-key test.
Updating Docker Desktop may also fix it; we have not verified that.

**`Cannot find module .../corepack/.../pnpm.cjs`.** An older Corepack can't launch
pnpm 12. Install pnpm directly (`npm install -g pnpm@12.23.0`) and make sure it comes
before any Corepack shim on your `PATH`.

## License

MIT. See [LICENSE](./LICENSE).

### API client contract

Run `make gen-client` after changing API routes or schemas. It exports OpenAPI without a running server and regenerates the TypeScript contract in `packages/api-client`; CI checks both files for drift. The web app uses the shared fetch client. Mobile uses it for all API calls (Jest-tested; Metro bundling has not been run here).
