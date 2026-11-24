# Full-Stack Boilerplate

A starter monorepo with a **FastAPI** backend (`api/`) and a **Next.js 15** frontend
(`client/`), run locally with Docker Compose and tested in GitHub Actions.

> [!WARNING]
> **Not production-ready yet.** This is the v1 baseline. A v2 upgrade (auth redesign,
> multi-tenancy, mobile app, real deploys) is in progress as a series of PRs. Known issues
> in the current code that you should not ship:
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

## What's included

**Backend (`api/`)**
- Python 3.13, FastAPI, SQLAlchemy 2.0 (sync) with `psycopg2`, PostgreSQL 16.
- Router → Service → Repository layering (`app/routers`, `app/services`, `app/repositories`).
- Email/password auth: bcrypt password hashing, HS256 JWT access tokens (python-jose),
  `GET/PATCH /auth/me`.
- Google OAuth 2.0 server-side redirect flow (`/auth/google/login`, `/auth/google/callback`),
  backend only, with the issues listed above.
- Example `items` CRUD, scoped to the signed-in user (`GET/POST /items`,
  `GET/PATCH/DELETE /items/{id}`).
- `GET /health` liveness endpoint (no database check).
- Alembic is configured (`api/alembic/`), but `versions/` is empty. The schema currently
  comes from `Base.metadata.create_all()` at startup.
- Poetry for dependency management (`api/pyproject.toml`, `api/poetry.lock`).

**Frontend (`client/`)**
- Next.js 15 (App Router), React 19, TypeScript (`strict: true`).
- Pages: `/`, `/auth/login`, `/auth/register`, `/items`.
- axios API client (`lib/api.ts`) that sends the JWT from `localStorage` and redirects to
  login on 401. Zustand auth store (`lib/auth-store.ts`).
- Plain CSS (`app/globals.css`). No component library, no Tailwind, no dark mode.
- No Google sign-in button and no frontend tests yet.

**Tooling**
- `docker-compose.yml`: `postgres`, `api` (hot reload, source mounted), `client`.
- The API image has a `HEALTHCHECK` (`api/healthcheck.py`, stdlib-only).
- `Makefile` wrapping Docker Compose (run `make help`).
- GitHub Actions (`.github/workflows/test.yml`):
  - backend: ruff, mypy (not strict mode), pytest with a coverage report (no threshold);
  - frontend: `next lint`, `tsc --noEmit`, `next build`;
  - `scripts/test-customize.sh`;
  - Docker images build, and the API container must report healthy.
- `.github/workflows/deploy.yml` is a manual placeholder. **Nothing is deployed.**
- `.pre-commit-config.yaml` is included but not run in CI.

## Quick start (Docker)

Prerequisites: Docker with Compose v2 (`docker compose`), Make, Git, OpenSSL.

```bash
git clone https://github.com/bhojnikhil/fullstack-boilerplate myapp
cd myapp

# Fill in the template placeholders (project name, display name, domain) and
# create api/.env (with a generated SECRET_KEY) and client/.env.local.
./scripts/customize.sh myapp "My App" myapp.com

make up
```

Then open:

- Frontend: http://localhost:3000. Create a user at `/auth/register`.
- API docs (Swagger UI): http://localhost:8000/docs (ReDoc: `/redoc`)

Docker Compose sets the API's environment in `docker-compose.yml` and does **not** read
`api/.env`. That file is for running the API directly on your machine (below).

Ports 5432, 8000 and 3000 must be free.

## Running without Docker

```bash
# Postgres: any local PostgreSQL 16 with a database named `boilerplate`, or:
docker compose up -d postgres

# API
cd api
poetry install
cp .env.example .env            # skip if customize.sh already created it
poetry run uvicorn app.main:app --reload

# Frontend (separate terminal)
cd client
npm ci
cp .env.example .env.local      # skip if customize.sh already created it
npm run dev
```

## Environment variables

**API** (`api/app/core/config.py`, read from the environment or `api/.env`):

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `postgresql://postgres:postgres@postgres:5432/boilerplate` | SQLAlchemy URL (psycopg2) |
| `SECRET_KEY` | `dev-secret-key-change-in-production` | JWT signing key. **Always set it.** The default is public. |
| `JWT_ALGORITHM` | `HS256` | |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 days) | |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | unset | Google OAuth is disabled when unset |
| `GOOGLE_REDIRECT_URI` | `http://localhost:8000/auth/google/callback` | |
| `FRONTEND_URL` | `http://localhost:3000` | Target of the OAuth redirect |
| `DEBUG` | `false` | |

CORS origins are hardcoded in `api/app/main.py` (`http://localhost:3000`,
`http://localhost`, `http://api:8000`).

**Frontend** (`client/.env.local`):

| Variable | Default | Notes |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Inlined at **build** time. Must be reachable from the browser. |

## Common commands

```bash
make help            # list all targets
make up / make down  # start / stop the stack
make ps              # service status, including the api health status
make logs            # follow logs
make test            # backend tests in the api container
make test-coverage   # backend tests with an HTML coverage report (api/htmlcov)
make lint            # ruff (in the api container) + next lint (on the host)
make typecheck       # mypy (in the api container) + tsc (on the host)
make format          # ruff format + prettier
make migrate         # alembic upgrade head (no migrations exist yet)
make migration NAME='add_column'
make db-shell        # psql into the dev database
make fresh           # wipe the DB volume, rebuild, start
```

Frontend targets run on the host and need `npm ci` in `client/` first.

## Project structure

```
api/
├── app/
│   ├── main.py          # FastAPI app, CORS, routers, create_all() at startup
│   ├── auth/            # password hashing, JWT, current-user dependencies
│   ├── core/            # settings (config.py), engine/session (db.py)
│   ├── models/          # User, OAuthAccount, Item
│   ├── schemas/         # Pydantic request/response models
│   ├── repositories/    # data access
│   ├── services/        # AuthService, OAuthService, ItemService
│   └── routers/         # /health, /auth, /items
├── alembic/             # migration environment (no versions yet)
├── tests/               # pytest (in-memory SQLite)
├── healthcheck.py       # container HEALTHCHECK probe
└── Dockerfile
client/
├── app/                 # App Router pages: /, /auth/login, /auth/register, /items
└── lib/                 # api.ts (axios), auth-store.ts (zustand)
scripts/
├── customize.sh         # placeholder replacement + local .env creation
└── test-customize.sh    # regression test for customize.sh
```

## Testing

```bash
# In Docker (stack running):
make test

# Or locally:
cd api && poetry run pytest
```

Backend tests use an in-memory SQLite database through a dependency override. The app's
startup hook still runs `create_all()` against `DATABASE_URL`, so a reachable Postgres is
required (CI provides one). There are no frontend tests yet.

## Adding a domain entity

Use `items` as the template: model (`app/models`) → schema (`app/schemas`) → repository
→ service → router, then register the router in `app/main.py` and add tests under
`api/tests/`. `CLAUDE_CONTEXT.md` has a longer walkthrough.

## Troubleshooting

**`Illegal instruction` (exit code 132) when building or running the API image on an Apple
M4 Mac.** We have seen OpenSSL, as loaded by the Python `cryptography` package, crash
inside Linux containers on an M4 Pro (Docker Desktop, engine 27.5). Setting
`OPENSSL_armcap=0` in the container environment avoids it (verified). The Dockerfile
already keeps Poetry from loading `cryptography` during the build. Updating Docker
Desktop may also fix it; we have not verified that.

## License

MIT. See [LICENSE](./LICENSE).
