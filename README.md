# Full-Stack Boilerplate

A starter monorepo with a **FastAPI** backend (`apps/api`) and a **Next.js 16** frontend
(`apps/web`). It uses uv for Python and pnpm workspaces + Turborepo for JavaScript, runs
locally with Docker Compose, and is tested in GitHub Actions.

> [!WARNING]
> **Not production-ready yet.** A v2 upgrade (auth redesign, multi-tenancy, mobile app,
> real deploys) is in progress as a series of PRs. Known issues in the current code that
> you should not ship:
>
> - Google OAuth: the `state` parameter is never verified (login CSRF), the JWT is put in
>   the redirect URL, and the frontend has no `/auth/callback` page, so Google sign-in
>   ends on a 404.
> - A Google identity is auto-linked to any existing account with the same email, and
>   registration does not verify email (pre-account-takeover risk).
> - Access tokens are 7-day JWTs with no refresh tokens, revocation, or rate limiting.
> - Google access/refresh tokens are requested (`access_type=offline`) and stored in
>   plaintext.

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
- Email/password registration and sign-in with bcrypt and JWT bearer tokens.
  Profile reads and updates use `/v1/auth/me`. The existing Google redirect endpoints
  are `/v1/auth/google/login` and `/v1/auth/google/callback`.
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
- axios API client (`lib/api.ts`) that sends the JWT from `localStorage` and redirects to
  login on 401. Zustand auth store (`lib/auth-store.ts`).

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
  `web` (production build; rebuild to see changes, or use `make dev` for hot reload).
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
    api and web as packaged, and require all to be healthy. The API smoke uses production
    settings, a temporary signing key and a host allowlist that excludes loopback. It
    checks HSTS, JSON logs and startup failure without a key. CI requires `/ready`
    to return HTTP 503 before explicit migrations and 2xx afterward. The web smoke
    requires direct 200 JSON responses from both association URLs and checks that
    runtime values appear on the privacy and account deletion pages. The API and web
    must run as unprivileged users with no mounts. Locally use `make smoke`.
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
- API docs (Swagger UI): http://localhost:8000/docs (ReDoc: `/redoc`)

`make up` waits for Postgres and runs Alembic in a one-off container before starting
the API and web. If you start services with Compose directly, run `make migrate-compose`
to apply migrations. The Compose development API bind-mounts `apps/api` and reads its
`.env`, with Compose's service environment taking precedence. The packaged image reads
its process environment.

Compose publishes Postgres and the API on IPv4 loopback (`127.0.0.1`) only, on host
ports 5432 and 8000 by default. The web port defaults to 3000. Set `POSTGRES_PORT`,
`API_PORT`, and `WEB_PORT` on the command line if those ports are in use.

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
and web together when updating to the `/v1` paths. If Google OAuth is configured,
also update the callback URI in Google and `GOOGLE_REDIRECT_URI`.

## Host development

Host-side commands (`make setup`, `make test`, `make lint`, `make dev`, ...) need:

| Tool | Version | Notes |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | 0.13.9 | Enforced by `required-version` in `apps/api/pyproject.toml`. uv installs Python 3.13 if needed. |
| Node.js | 26 (LTS) | `.nvmrc` |
| pnpm | 12.23.0 | Pinned in `package.json` `packageManager`. Node 25+ has no Corepack, so install it with `npm install -g pnpm@12.23.0`. |

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

| Variable | Default | Notes |
| --- | --- | --- |
| `ENV` | `production` | Allowed values are `development`, `test`, `staging`, and `production`. The Compose dev service and `.env.example` set `development`. Other environments use JSON logs and send HSTS. |
| `DATABASE_URL` | Local Compose Postgres in development only | Required in test, staging and production. Use the Neon pooled URL for the app. |
| `MIGRATION_DATABASE_URL` | Falls back to `DATABASE_URL` | Use the Neon direct URL for Alembic. Preserve provider connection options such as `sslmode=require`. |
| `SECRET_KEY` | Local development fallback only | Set a unique secret of at least 32 characters in test, staging and production. |
| `JWT_ALGORITHM` | `HS256` | Signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` | JWT lifetime in minutes. |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array of explicit `http://` or `https://` origins with an optional port. Origins are lowercased. Omit paths, even a trailing slash. |
| `TRUSTED_HOSTS` | `["localhost","127.0.0.1","[::1]"]` | JSON array of permitted hosts without ports. Staging and production reject `*`. Probes accept any Host. |
| `MAX_REQUEST_BODY_BYTES` | `1048576` | Maximum HTTP body size in bytes, including chunked requests. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Unset | Optional pair. Set both to enable Google OAuth. |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/v1/auth/google/callback` | Must match the Google OAuth client configuration. |
| `FRONTEND_URL` | `http://localhost:3000` | Browser destination for the legacy OAuth redirect. |
| `HEALTHCHECK_URL` | `http://127.0.0.1:8000/health` | Optional override for the container probe, which reads the process environment. |

Run the Alembic upgrade with the direct connection before starting new API
instances. `/ready` returns 503 if the DB is unreachable, unmigrated or behind the
image. Unknown revisions are treated as newer; the API logs their IDs once per distinct
set per process. During a rolling
release, keep migrations compatible with instances of the previous release. See [ADR 0004](docs/adr/0004-async-postgres.md).

**Web** ([`.env.example`](apps/web/.env.example))

| Variable | Default | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Inlined at **build** time. Must be reachable from the browser. For the Docker image it is a build arg (`--build-arg NEXT_PUBLIC_API_URL=...`; Compose reads it from your shell or a root `.env`); env files are not copied into the image. |
| `WEB_LEGAL_APP_NAME` | `[App name]` placeholder | Name shown in the header, page titles, and public policy and deletion templates. |
| `WEB_LEGAL_DOMAIN` | `[Site domain]` placeholder | Domain shown in the privacy and terms templates. |
| `WEB_SUPPORT_EMAIL` | Unset | Monitored mailbox for deletion requests sent from `/account-deletion`. |
| `ANDROID_PACKAGE_NAME` | Unset | Android application ID, for example `com.example.app`. |
| `ANDROID_SHA256_CERT_FINGERPRINTS` | Unset | Comma-separated, colon-delimited SHA-256 signing certificate fingerprints. Include the Play App Signing certificate for Play builds. |
| `IOS_TEAM_ID` | Unset | 10-character Apple Developer Team ID. |
| `IOS_BUNDLE_ID` | Unset | iOS bundle identifier, for example `com.example.app`. |
| `IOS_APPLINK_PATHS` | `/app/*` | Comma-separated URL paths beginning with `/`. Supports `*` wildcards. Include the email-verification, password-reset and invite paths that the mobile app handles. |

Host development and `make up` both read the legal, support and association
settings from the optional `apps/web/.env.local` at **runtime**. After changing
that file, run `make up` again to apply the values in Compose. When running the
standalone image directly, pass the variables to the container, for example with
`docker run -e WEB_SUPPORT_EMAIL=support@example.com …`.

### Public pages and mobile links

- `scripts/customize.sh PROJECT_NAME "App Name" DOMAIN` fills the legal app and domain
  values in the web env example. It copies that example to `apps/web/.env.local` when the
  local file is absent. Run `make up` and visit `/privacy` to see the configured values.
  Before publishing, complete the privacy and terms templates and the account deletion
  template, including the in-app workflow, the data deleted or retained, and retention
  periods. Set `WEB_SUPPORT_EMAIL` to a monitored mailbox.
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

## API contracts

`GET /v1/items?limit=25` returns `{"items": [...], "next_cursor": "..."}`.
Pass the returned cursor as `cursor` on the next request. The maximum page size
is 100 and a null cursor marks the last page.

`POST /v1/items`, `PATCH/DELETE /v1/items/{item_id}` and `PATCH /v1/auth/me` accept an
optional `Idempotency-Key` of up to 128 visible ASCII characters. Retry with the
same user, key, method, path, query string, media type and identical body bytes.
`Content-Type` parameters such as `charset` are ignored. Preserve the serialized JSON,
including whitespace and property order. A retry replays the committed status and
response body for up to 24 hours. Reusing the key for a different request returns
422. An overlapping request with the same user and key returns 409. Failed transactions leave the key available for retry.
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
for both association URLs and the runtime values on `/privacy` and `/account-deletion`.

`make test` creates and uses the dedicated `boilerplate_test` database on Compose
Postgres. To use another dedicated Postgres database, run
`make test TEST_DATABASE_URL=postgresql://user:password@host/dbname`. With pytest
directly, run from `apps/api` with `ENV=test`, `DATABASE_URL` set to that database,
and a throwaway `SECRET_KEY` (for example, `export SECRET_KEY="$(openssl rand -hex 32)"`).
For a targeted run, use `uv run --locked pytest --no-cov tests/test_settings.py` to
skip the suite-wide coverage gate. The test user needs
permission to create schemas. Each database test applies Alembic to its own schema
and drops the schema afterward. HTTP tests use httpx's ASGI transport and real
request transactions. CI applies migrations to its Postgres 16 service, runs
`alembic check` for schema drift and runs the same suite. Plain pytest, `make test`
and CI share the 96.0% branch-aware coverage gate in `apps/api/pyproject.toml`,
with greenlet and thread tracing enabled.

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
