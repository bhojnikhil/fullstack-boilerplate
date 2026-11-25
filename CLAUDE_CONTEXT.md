# {{APP_NAME}} Full-Stack Boilerplate Context

The [README](README.md) describes the auth model, current limitations and local setup.
The API uses FastAPI and async SQLAlchemy with psycopg 3. The web app uses Next.js 16,
React 19, Tailwind CSS 4, shadcn/ui, axios and Zustand.

## Layout

```
apps/api/
  app/main.py            FastAPI app, router registration, app-wide services (app.state)
  app/core/              settings, request session, errors, middleware, health, security
                         primitives, rate limiter, audit log, client info
  app/integrations/      email (backends + templates), Expo push, S3 storage, Google ID tokens,
                         Pwned Passwords
  app/jobs/              Postgres job queue, handlers, periodic purge, worker (python -m app.jobs)
  app/modules/devices/   push token registration, sending and receipt processing
  app/modules/auth/      accounts, sessions, tokens, Google sign-in, /v1/auth and /v1/me
  app/modules/items/     user-scoped CRUD example
  alembic/               database migrations
  tests/                 pytest integration and unit tests
apps/web/                Next.js pages and axios client
packages/config/         shared TypeScript, ESLint and Prettier config
docs/adr/                architecture decisions
scripts/                 template customization and container checks
```

## Adding an API module

1. Define models in `app/modules/<name>/models.py` and import them in `alembic/env.py`.
   Use UUID primary keys and `created_at` and `updated_at` timestamps for domain entities.
   Use `timestamptz` for UTC instants and `date` for calendar dates interpreted in the
   workspace timezone when workspaces are available. Store money as integer minor units
   paired with an ISO currency code.
2. Run `make migration name=describe_change`, review the resulting migration and apply it
   with `make migrate`. Alembic is the schema source. The app starts independently of Postgres.
3. Put queries in `repository.py`. Repositories receive an `AsyncSession` and may flush
   and refresh ORM instances. The session dependency owns the commit and rollback.
4. Put business rules in `service.py`. Services take repositories and raise
   `DomainError` for expected failures. Define public error codes and status mappings in
   `app/core/errors.py`.
5. Define request and response schemas in `schemas.py`. Request models use
   `ConfigDict(extra="forbid")`. HTTP errors use the shared `ErrorEnvelope`.
6. Define routes in `router.py` using `API_PREFIX` and register the router in `app/main.py`.
   Use a stable module tag and handler name for each operation ID. Use
   `app.core.db.RequestSession` so dependency resolution shares one transaction across
   authentication, idempotency and business operations. The dependency commits after
   serialization and before FastAPI sends a success response.
7. Add tests in `apps/api/tests`. Use the real Postgres fixtures for DB functionality and
   `httpx.AsyncClient` for HTTP assertions. The items module demonstrates keyset pagination
   and idempotent mutation responses. `tests/conftest.py` has `sign_in`/`bearer` helpers
   that create real sessions, plus `outbox` (sent emails; the `client` runs the worker after every request, use `job_context` for the queue and fake push) and `google` (fake verifier).

Conventions added with the auth redesign:

- A `DomainError(..., commit=True)` commits the request's writes before the error response.
  Use it only when the service wrote exactly the side effects that must survive (an audit
  event, a revoked session). Other errors roll back.
- Rate-limit counters (`app.core.ratelimit`) use their own short transactions so they
  survive the request's rollback. Add rules next to the module that uses them.
- Record security-relevant events with `app.core.audit.record_event`. Never put tokens,
  passwords, email addresses or IPs in `details`; use `keyed_digest` when correlation helps.
- Send email with the request-scoped `Mailer` (`app.integrations.email.Mail`). It enqueues a
  `send_email` job in the request's transaction; the worker sends it after commit, with
  retries. Enqueue other work with `app.jobs.queue.enqueue(db, kind, payload)` and register
  the handler in `app/jobs/handlers.py`. Never put secrets in payloads or log their contents.
- `AppVersionGate` (`app/core/appversion.py`) 426s old mobile clients; `/v1/meta` is exempt.
- Store opaque tokens as `token_digest` (SHA-256); compare secrets with
  `constant_time_equals`. Expiry times are computed and compared with the application
  clock, not the database's `now()`.
- Modules that own user data register an `AccountDeletionHook` in `create_app`
  (`app.state.account_deletion_hooks`) to block or clean up before `DELETE /v1/me`.

## Runtime contracts

- `/v1/auth` serves registration, password and Google sign-in, refresh, logout, email
  verification, password reset, re-authentication, Google link/unlink and session
  management; `/v1/me` serves the profile, password and email changes and account deletion.
  Access tokens last 15 minutes and are checked against an active session on every request.
  Refresh tokens rotate on every use; reuse revokes the session. `X-Platform: web` clients
  get the refresh token as an httpOnly cookie on `/v1/auth/refresh` (CSRF: `Origin` allowlist
  plus `X-CSRF-Token`); other clients get it in the body. See ADRs 0006 to 0008.
- The web pages are at `/auth/login` and `/auth/register`. The web keeps the access token in
  memory and refreshes it with the cookie.
- `/v1/items` uses the signed-in user's ID and sorts by creation time and UUID. The list response
  includes `items` and `next_cursor`.
- Signed-in item mutations and profile updates can take an `Idempotency-Key`. The key
  is scoped to the user, with a 24-hour replay window. The response record is written in
  the same Postgres transaction as the mutation. See [ADR 0004](docs/adr/0004-async-postgres.md).
- Request logs contain the request ID, route template, method, status, duration and
  user ID when available. Exceptions include stack frames and types. Keep messages,
  locals, request bodies, raw URLs and query strings, credentials and provider responses
  out of exception logs. Development uses console logs with redacted tracebacks;
  the API and Alembic use JSON logs outside development.
- The API defaults to `ENV=production` and requires an explicit signing key and database URL
  in test, staging and production; staging and production also require `JWT_SECRET_KEY`,
  SMTP email, Postgres rate limiting and an `https` `WEB_URL`. Compose development sets
  `ENV=development`, sends email to Mailpit through the worker and publishes every port only on IPv4 loopback.
- The container probes `/health` for liveness. Both probes bypass the host allowlist.
  `/ready` rejects an unreachable, unmigrated or behind database. An unknown revision is
  accepted with a warning that names the unknown IDs once per set per process. Migration
  0003 requires a coordinated cutover: stop old API instances before migrating. Run
  Alembic using the direct connection when the application uses a pooler.

## Development and checks

```bash
./scripts/customize.sh myapp "My App" myapp.com
make setup                        # locked uv and pnpm installs
make up                           # Compose Postgres, explicit migrations, API, web, Mailpit
make dev                          # Compose Postgres + API, Next.js dev server on host
make test                         # API tests on dedicated Compose Postgres
make lint typecheck fmt-check     # Ruff, strict mypy, ESLint, tsc and Prettier
make build-web                    # production Next.js build
make smoke                        # packaged API and web in production mode: probes, sign-up
                                  # email over SMTP, refresh cookie, association files
pnpm --filter web test            # Vitest and React Testing Library
pnpm --filter web test:e2e        # public web smoke with Playwright Chromium
```

For targeted API tests, run from `apps/api` with `ENV=test` and a dedicated Postgres
`DATABASE_URL` and a throwaway `SECRET_KEY` (`export SECRET_KEY="$(openssl rand -hex 32)"`).
Use `uv run --locked pytest --no-cov tests/test_settings.py` to skip the suite-wide
coverage gate for a targeted run. The fixtures apply Alembic in a fresh schema for each database test,
including tests with concurrent requests. CI upgrades its Postgres service and runs
`alembic check` before pytest. Plain pytest, `make test` and CI enforce the 96.0%
branch-aware gate configured in `apps/api/pyproject.toml`, with greenlet and thread tracing.

Check the current stable registry versions before choosing dependency versions.
Pin exact versions and update the corresponding lockfile. Keep local env files and
build output out of Git. Use [apps/api/.env.example](apps/api/.env.example) for the
API settings and [apps/web/.env.example](apps/web/.env.example) for web configuration.
