# Full-Stack Boilerplate

A starter monorepo with a **FastAPI** backend (`apps/api`) and a **Next.js 15** frontend
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
> - `SECRET_KEY` falls back to a public default when unset.
> - Access tokens are 7-day JWTs with no refresh tokens, revocation, or rate limiting.
> - Google access/refresh tokens are requested (`access_type=offline`) and stored in
>   plaintext.
> - Tables are created with `create_all()` at API startup; there are no Alembic
>   migrations yet.
> - Each repository method commits on its own (no request-level transactions), and
>   services raise `HTTPException` directly.

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
- Python 3.13, FastAPI, SQLAlchemy 2.1 (sync) with psycopg 3, PostgreSQL 16.
- Router → Service → Repository layering (`app/routers`, `app/services`, `app/repositories`).
- Email/password auth: bcrypt password hashing, HS256 JWT access tokens (python-jose),
  `GET/PATCH /auth/me`. Requests without a token get `401`.
- Google OAuth 2.0 server-side redirect flow (`/auth/google/login`, `/auth/google/callback`),
  backend only, with the issues listed above.
- Example `items` CRUD, scoped to the signed-in user (`GET/POST /items`,
  `GET/PATCH/DELETE /items/{id}`).
- `GET /health` liveness endpoint (no database check).
- Alembic is configured (`apps/api/alembic/`), but `versions/` is empty. The schema
  currently comes from `Base.metadata.create_all()` at startup.
- Dependencies managed with uv: exact pins in `pyproject.toml`, locked in `uv.lock`
  ([ADR 0001](docs/adr/0001-python-tooling-uv.md)).

**Frontend (`apps/web`)**
- Next.js 15 (App Router), React 19, TypeScript 6 (`strict`), extending the shared
  config in `packages/config`.
- Pages: `/`, `/auth/login`, `/auth/register`, `/items`.
- axios API client (`lib/api.ts`) that sends the JWT from `localStorage` and redirects to
  login on 401. Zustand auth store (`lib/auth-store.ts`).
- Plain CSS (`app/globals.css`). No component library, no Tailwind, no dark mode.
- No Google sign-in button and no frontend tests yet.

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
  - **api**: `uv sync --locked`, ruff check, ruff format --check, mypy (not strict mode),
    pytest with a coverage report (no threshold);
  - **web**: `pnpm install --frozen-lockfile`, Prettier check, then ESLint, `tsc` and
    `next build` via Turborepo;
  - **scripts**: `scripts/test-customize.sh`;
  - **docker**: `scripts/test-dockerignore.sh`, build all images, then start postgres,
    api and web as packaged (`docker-compose.smoke.yml`: no source mounts) and require
    all to be healthy and non-root. Locally: `make smoke`.
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

Docker Compose sets the API's environment in `docker-compose.yml` and does **not** read
`apps/api/.env`. That file is for running the API directly on your machine (below).

Ports 5432, 8000 and 3000 must be free.

## Host development

Host-side commands (`make setup`, `make test`, `make lint`, `make dev`, ...) need:

| Tool | Version | Notes |
| --- | --- | --- |
| [uv](https://docs.astral.sh/uv/) | 0.13.9 | Enforced by `required-version` in `apps/api/pyproject.toml`. uv installs Python 3.13 if needed. |
| Node.js | 26 (LTS) | `.nvmrc` |
| pnpm | 12.23.0 | Pinned in `package.json` `packageManager`. Node 25+ has no Corepack, so install it with `npm install -g pnpm@12.23.0`. |

```bash
make setup                      # uv sync --locked + pnpm install --frozen-lockfile
docker compose up -d postgres   # or `make up`
make test                       # API tests against the compose Postgres (localhost:5432)
make dev                        # postgres + api in Docker, web dev server on the host
```

To run the API on the host instead of in Docker:

```bash
cd apps/api
cp .env.example .env            # skip if customize.sh already created it
uv run uvicorn app.main:app --reload
```

## Environment variables

**API** (`apps/api/app/core/config.py`, read from the environment or `apps/api/.env`):

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://postgres:postgres@postgres:5432/boilerplate` | SQLAlchemy URL; `postgresql://` uses psycopg 3 |
| `SECRET_KEY` | `dev-secret-key-change-in-production` | JWT signing key. **Always set it.** The default is public. |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 days) | |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | unset | Google OAuth is disabled when unset |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/auth/google/callback` | |
| `FRONTEND_URL` | `http://localhost:3000` | Target of the OAuth redirect |
| `DEBUG` | `false` | |

CORS origins are hardcoded in `apps/api/app/main.py` (`http://localhost:3000`,
`http://localhost`, `http://api:8000`).

The Makefile's host-side Python targets (`test`, `migrate`, `migration`) default
`DATABASE_URL` to the compose Postgres at `localhost:5432`. Override it with
`make test DATABASE_URL=...`.

**Web** (`apps/web/.env.local`):

| Variable | Default | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Inlined at **build** time. Must be reachable from the browser. For the Docker image it is a build arg (`--build-arg NEXT_PUBLIC_API_URL=...`; Compose reads it from your shell or a root `.env`); env files are not copied into the image. |

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
make migrate                   # alembic upgrade head (no migrations exist yet)
make migration name=add_column # autogenerate a migration
make db-shell                  # psql into the dev database
make fresh                     # wipe the DB volume, rebuild, start
make smoke                     # build + start all images as packaged, wait for healthy
```

## Testing

```bash
docker compose up -d postgres
make test
```

API tests use an in-memory SQLite database through a dependency override. The app's
startup hook still runs `create_all()` against `DATABASE_URL`, so a reachable Postgres is
required (CI provides one). There are no frontend tests yet.

## Adding a domain entity

Use `items` as the template: model (`app/models`) → schema (`app/schemas`) → repository
→ service → router, then register the router in `app/main.py` and add tests under
`apps/api/tests/`. `CLAUDE_CONTEXT.md` has a longer walkthrough.

## Troubleshooting

**`Illegal instruction` (exit code 132) when running the API in Docker on an Apple M4
Mac.** We have seen OpenSSL, as loaded by the Python `cryptography` package, crash inside
Linux containers on an M4 Pro (Docker Desktop, engine 27.5). Setting `OPENSSL_armcap=0`
in the container environment avoids it (verified). Updating Docker Desktop may also fix
it; we have not verified that.

**`Cannot find module .../corepack/.../pnpm.cjs`.** An older Corepack can't launch
pnpm 12. Install pnpm directly (`npm install -g pnpm@12.23.0`) and make sure it comes
before any Corepack shim on your `PATH`.

## License

MIT. See [LICENSE](./LICENSE).
