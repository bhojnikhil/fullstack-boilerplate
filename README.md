# Full-Stack Boilerplate

A starter monorepo with a **FastAPI** backend (`apps/api`) and a **Next.js 16** frontend
(`apps/web`). It uses uv for Python and pnpm workspaces + Turborepo for JavaScript, runs
locally with Docker Compose, and is tested in GitHub Actions.

> [!WARNING]
> **Not production-ready yet.** A v2 upgrade (multi-tenancy, background jobs, mobile app,
> web rebuild, real deploys) is in progress as a series of PRs. Gaps in the current code:
>
> - Emailed links open web pages (`/auth/verify-email`, `/auth/reset-password`,
>   `/auth/confirm-email`, `/auth/forgot-password`) that the web app does not have yet;
>   they arrive with the web rebuild. Until then, post the token from the email to the API
>   (see [Authentication](#authentication)).
> - Email is sent by an in-process task after the response. A crash or SMTP outage at that
>   moment loses the message; a durable job queue with retries is planned.
> - Expired sessions, refresh tokens, emailed tokens and rate-limit rows are not purged yet.
> - The web app has no Google sign-in button yet (the API endpoint exists).

## Repository layout

```
apps/
  api/            FastAPI service (Python, uv)
  web/            Next.js app (pnpm workspace package "web")
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
- Email through a small provider interface: console (development), SMTP, and an
  in-memory backend for tests. Compose runs [Mailpit](https://mailpit.axllent.org/) to
  view messages locally.
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

**Tooling**

- pnpm workspaces + Turborepo for `lint`, `typecheck`, `build`, `dev`
  ([ADR 0002](docs/adr/0002-js-monorepo-pnpm-turborepo.md)).
- Formatting: ruff format (Python) and Prettier (`apps/web`, `packages`), both enforced
  in CI.
- Docker images ([ADR 0003](docs/adr/0003-container-images.md)):
  - API: multi-stage; the default `runtime` target is slim (no compilers, uv, pip or
    tests) and runs as an unprivileged user; a `dev` target is used by Compose.
  - Web: Next.js standalone server, running as the unprivileged `node` user.
  - Both have `HEALTHCHECK`s that require a 2xx response and don't follow redirects.
- `docker-compose.yml`: `postgres`, `api` (`dev` target, hot reload, source mounted),
  `web` (production build; rebuild to see changes, or use `make dev` for hot reload) and
  `mailpit` (SMTP on 1025, inbox UI on 8025). The API sends its email to Mailpit.
- `apps/api/.dockerignore` and `apps/web/Dockerfile.dockerignore` keep env files, keys
  and local DBs (at any depth) out of images.
- GitHub Actions (`.github/workflows/ci.yml`), with every third-party action pinned to a
  commit SHA:
  - **api**: locked uv install, Ruff lint and format, strict mypy, Alembic upgrade and
    drift check, and pytest on Postgres 16 with a 96.0% branch-aware coverage gate.
  - **web**: `pnpm install --frozen-lockfile`, Prettier check, then ESLint, `tsc` and
    `next build` via Turborepo, Vitest, and Playwright against the standalone build;
  - **scripts**: `scripts/test-customize.sh`, `scripts/test-check-containers.sh`;
  - **docker**: `scripts/test-dockerignore.sh`, build all images, then start postgres,
    mailpit, api and web as packaged, and require all to be healthy. The API smoke uses
    production settings, temporary signing keys and a host allowlist that excludes
    loopback. It checks HSTS, JSON logs, startup failure without `SECRET_KEY` or
    `JWT_SECRET_KEY`, and a sign-up whose verification email is delivered over SMTP to
    Mailpit, verified, and followed by a web sign-in that sets a `Secure`, `HttpOnly`,
    `SameSite=Strict` refresh cookie. CI requires `/ready` to return HTTP 503 before
    explicit migrations and 2xx afterward. The web smoke requires direct 200 JSON
    responses and one-hour cache headers from both association URLs. It checks security
    headers and the runtime values in the privacy and account deletion pages. The API and
    web must run as unprivileged users with no mounts. Locally use `make smoke`.
- Dependabot groups weekly updates for uv, pnpm, Dockerfiles, Compose and GitHub Actions.
- `.github/workflows/deploy.yml` is a manual placeholder. **Nothing is deployed.**
- `.pre-commit-config.yaml` is included but not run in CI.

## Quick start (Docker)

Prerequisites: Docker with Compose v2 (`docker compose`), Make, Git, OpenSSL.

```bash
git clone https://github.com/bhojnikhil/fullstack-boilerplate myapp
cd myapp

# Fill in the remaining template placeholders (currently the app display name)
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
- Existing users start unverified and must prove inbox ownership before signing in.
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

| Variable                                                                     | Default                                           | Notes                                                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------- | ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ENV`                                                                        | `production`                                      | Allowed values are `development`, `test`, `staging`, and `production`. The Compose dev service and `.env.example` set `development`. Other environments use JSON logs and send HSTS.                                                                                                                              |
| `DATABASE_URL`                                                               | Local Compose Postgres in development only        | Required in test, staging and production. Use the Neon pooled URL for the app.                                                                                                                                                                                                                                    |
| `MIGRATION_DATABASE_URL`                                                     | Falls back to `DATABASE_URL`                      | Use the Neon direct URL for Alembic. Preserve provider connection options such as `sslmode=require`.                                                                                                                                                                                                              |
| `SECRET_KEY`                                                                 | Local development fallback only                   | Server-side HMAC secret (IP hashes, CSRF tokens, rate-limit and audit identifiers). Set a unique secret of at least 32 characters in test, staging and production; the repository's published keys are rejected, even with surrounding whitespace. Rotating it signs web sessions out (their CSRF tokens change). |
| `JWT_SECRET_KEY`                                                             | Derived from `SECRET_KEY` in development and test | Access-token signing key. Required in staging and production: unique, different from `SECRET_KEY`, and at least 32/48/64 bytes for HS256/HS384/HS512. Rotating it makes clients refresh once.                                                                                                                     |
| `JWT_ALGORITHM`                                                              | `HS256`                                           | `HS256`, `HS384` or `HS512`.                                                                                                                                                                                                                                                                                      |
| `JWT_ISSUER` / `JWT_AUDIENCE`                                                | `boilerplate-api`                                 | `iss`/`aud` claims, checked on every request.                                                                                                                                                                                                                                                                     |
| `ACCESS_TOKEN_EXPIRE_MINUTES`                                                | `15`                                              | Access-token lifetime, 1 to 60 minutes.                                                                                                                                                                                                                                                                           |
| `REFRESH_TOKEN_EXPIRE_DAYS`                                                  | `30`                                              | Idle timeout: each refresh extends the session by this much.                                                                                                                                                                                                                                                      |
| `SESSION_MAX_AGE_DAYS`                                                       | `90`                                              | Absolute session lifetime; then the user signs in again.                                                                                                                                                                                                                                                          |
| `REAUTHENTICATION_MAX_AGE_MINUTES`                                           | `10`                                              | How recent a sign-in or re-authentication on the session must be for account deletion, email changes and Google (un)linking.                                                                                                                                                                                      |
| `EMAIL_TOKEN_EXPIRE_HOURS`                                                   | `24`                                              | Lifetime of email verification and email-change links.                                                                                                                                                                                                                                                            |
| `PASSWORD_RESET_EXPIRE_MINUTES`                                              | `30`                                              | Lifetime of password reset links.                                                                                                                                                                                                                                                                                 |
| `PASSWORD_BREACH_CHECK`                                                      | `false`                                           | Reject new passwords found in Have I Been Pwned (k-anonymity range API; fails open).                                                                                                                                                                                                                              |
| `APP_NAME`                                                                   | `Boilerplate App`                                 | Product name in emails.                                                                                                                                                                                                                                                                                           |
| `WEB_URL`                                                                    | `http://localhost:3000`                           | Base URL of the web app for emailed links. Staging and production require `https`.                                                                                                                                                                                                                                |
| `GOOGLE_AUTH_ENABLED`                                                        | `false`                                           | Enables `POST /v1/auth/google`. Requires at least one client ID below.                                                                                                                                                                                                                                            |
| `GOOGLE_WEB_CLIENT_ID` / `GOOGLE_ANDROID_CLIENT_ID` / `GOOGLE_IOS_CLIENT_ID` | Unset                                             | OAuth client IDs (`*.apps.googleusercontent.com`) whose ID tokens are accepted. No client secret is needed.                                                                                                                                                                                                       |
| `EMAIL_BACKEND`                                                              | `console`                                         | `console` (prints messages and links; development), `smtp`, or `memory` (tests). Staging and production require `smtp`. Compose uses `smtp` with Mailpit.                                                                                                                                                         |
| `EMAIL_FROM`                                                                 | `Boilerplate App <no-reply@localhost>`            | Sender address.                                                                                                                                                                                                                                                                                                   |
| `SMTP_HOST` / `SMTP_PORT`                                                    | `localhost` / `1025`                              | SMTP server.                                                                                                                                                                                                                                                                                                      |
| `SMTP_SECURITY`                                                              | `none`                                            | `none`, `starttls`, or `tls` (implicit TLS).                                                                                                                                                                                                                                                                      |
| `SMTP_USERNAME` / `SMTP_PASSWORD`                                            | Unset                                             | Set both or neither.                                                                                                                                                                                                                                                                                              |
| `SMTP_ALLOW_INSECURE`                                                        | `false`                                           | Explicitly allow an unauthenticated plaintext local relay outside development/test. Authenticated SMTP always requires TLS.                                                                                                                                                                                       |
| `SMTP_TIMEOUT_SECONDS`                                                       | `10`                                              | SMTP connection timeout.                                                                                                                                                                                                                                                                                          |
| `RATE_LIMIT_BACKEND`                                                         | `postgres`                                        | `postgres`, or `memory` (per process; development and test only).                                                                                                                                                                                                                                                 |
| `CORS_ORIGINS`                                                               | `["http://localhost:3000"]`                       | JSON array of explicit `http://` or `https://` origins with an optional port. Origins are lowercased and default ports (`:443`, `:80`) are dropped, as browsers send them. Omit paths, even a trailing slash. Also the allowlist for the `Origin` check on web sign-in and cookie refresh.                        |
| `TRUSTED_HOSTS`                                                              | `["localhost","127.0.0.1","[::1]"]`               | JSON array of permitted hosts without ports. Staging and production reject `*`. Probes accept any Host.                                                                                                                                                                                                           |
| `MAX_REQUEST_BODY_BYTES`                                                     | `1048576`                                         | Maximum HTTP body size in bytes, including chunked requests.                                                                                                                                                                                                                                                      |
| `HEALTHCHECK_URL`                                                            | `http://127.0.0.1:8000/health`                    | Optional override for the container probe, which reads the process environment.                                                                                                                                                                                                                                   |

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

## Common commands

```bash
make help                      # list all targets
make setup                     # install locked Python + JS dependencies
make up / make down            # start / stop the Docker stack
make ps / make logs            # status (including health) / follow logs
make dev                       # api in Docker + web dev server with hot reload
make test                      # API tests (pytest)
make lint                      # ruff check + ESLint
make typecheck                 # mypy + tsc
make fmt / make fmt-check      # ruff format + Prettier (write / check)
make build-web                 # production build of the web app
make migrate                   # alembic upgrade head from the host
make migrate-compose           # alembic upgrade head in a one-off Compose container
make migration name=add_column # autogenerate a migration
make db-shell                  # psql into the dev database
make fresh                     # wipe the DB volume, rebuild, start
make smoke                     # packaged containers, health and production API/web checks
```

## Authentication

Design records: [ADR 0006](docs/adr/0006-auth-tokens-and-sessions.md) (tokens, sessions,
web and mobile transport), [ADR 0007](docs/adr/0007-google-id-token-sign-in.md) (Google
sign-in and account linking) and [ADR 0008](docs/adr/0008-rate-limits-email-audit.md)
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
A new registration for an unverified address replaces the pending credential and link.
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
