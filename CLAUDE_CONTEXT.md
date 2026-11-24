# {{APP_NAME}} Full-Stack Boilerplate Context

The [README](README.md) lists the current auth limitations and local setup commands.
The API uses FastAPI and async SQLAlchemy with psycopg 3. The web app uses Next.js 16,
React 19, Tailwind CSS 4, shadcn/ui, axios and Zustand.

## Layout

```
apps/api/
  app/main.py            FastAPI app and router registration
  app/core/              settings, request session, error handlers, middleware and health
  app/modules/auth/      users, Google accounts, password login and profile
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
   and idempotent mutation responses.

## Runtime contracts

- `/v1/auth` serves register, login, profile and the legacy Google redirect flow.
  The web pages are at `/auth/login` and `/auth/register`. The web uses bearer access tokens
  from localStorage.
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
  in test, staging and production. Compose development sets `ENV=development` and publishes
  the API and Postgres only on IPv4 loopback.
- The container probes `/health` for liveness. Both probes bypass the host allowlist.
  `/ready` rejects an unreachable, unmigrated or behind database. An unknown revision is
  accepted with a warning that names the unknown IDs once per set per process to support
  rolling deploys. Run Alembic using the direct
  connection when the application uses a pooler.

## Development and checks

```bash
./scripts/customize.sh myapp "My App" myapp.com
make setup                        # locked uv and pnpm installs
make up                           # Compose Postgres, explicit migrations, API and web
make dev                          # Compose Postgres + API, Next.js dev server on host
make test                         # API tests on dedicated Compose Postgres
make lint typecheck fmt-check     # Ruff, strict mypy, ESLint, tsc and Prettier
make build-web                    # production Next.js build
make smoke                        # packaged API in production mode, migrations and probes
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
