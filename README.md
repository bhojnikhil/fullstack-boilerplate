# Full-Stack Boilerplate

A starter monorepo with a **FastAPI** backend (`apps/api`), a **Next.js 16** frontend
(`apps/web`) and an **Expo** (React Native) mobile app foundation (`apps/mobile`). It uses
uv for Python and pnpm workspaces + Turborepo for JavaScript, runs locally with Docker
Compose, and is tested in GitHub Actions.

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

**Mobile (`apps/mobile`)**: foundation only; see [Mobile](#mobile). It does not call
the API yet: no sign-in, no data.
- Expo SDK 58, React Native 0.88, TypeScript 6 (`strict` plus the shared
  `packages/config` options), Expo Router with `(auth)` and `(app)` route groups and
  placeholder screens (sign in, sign up, items, settings) in a tab layout.
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
  `web` (production build; rebuild to see changes, or use `make dev` for hot reload).
- `apps/api/.dockerignore` and `apps/web/Dockerfile.dockerignore` keep env files, keys
  and local DBs (at any depth) out of images.
- GitHub Actions (`.github/workflows/ci.yml` and `mobile.yml`), with every third-party
  action pinned to a commit SHA:
  - **api**: locked uv install, Ruff lint and format, strict mypy, Alembic upgrade and
    drift check, and pytest on Postgres 16 with a 96.0% branch-aware coverage gate.
  - **web**: `pnpm install --frozen-lockfile`, Prettier check, then ESLint, `tsc` and
    `next build` via Turborepo (ESLint and `tsc` run for every JS package, including
    mobile), Vitest, and Playwright against the standalone build;
  - **scripts**: `scripts/test-customize.sh`, `scripts/test-check-containers.sh`;
  - **docker**: `scripts/test-dockerignore.sh`, build all images, then start postgres,
    api and web as packaged, and require all to be healthy. The API smoke uses production
    settings, a temporary signing key and a host allowlist that excludes loopback. It
    checks HSTS, JSON logs and startup failure without a key. CI requires `/ready`
    to return HTTP 503 before explicit migrations and 2xx afterward. The web smoke
    requires direct 200 JSON responses and one-hour cache headers from both association
    URLs. It checks security headers and the runtime values in the privacy and account
    deletion pages. The API and web must run as unprivileged users with no mounts.
    Locally use `make smoke`.
  - **mobile** (`mobile.yml`, only when `apps/mobile`, `packages`, the lockfile or root
    JS config change): Prettier check, `tsc`, ESLint, Jest and `expo-doctor`, each as
    its own step.
- Dependabot groups weekly updates for uv, pnpm, Dockerfiles, Compose and GitHub Actions.
- `.github/workflows/deploy.yml` is a manual placeholder. **Nothing is deployed.**

## Quick start (Docker)

Prerequisites: Docker with Compose v2 (`docker compose`), Make, Git, OpenSSL.

```bash
git clone https://github.com/bhojnikhil/fullstack-boilerplate myapp
cd myapp

# Fill in template placeholders and create missing local env files.
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

Package names in the lockfiles remain fixed. The script creates missing local
env files from their corresponding `.env.example` files. For the API it
generates a `SECRET_KEY` in `apps/api/.env` and keeps the secret marker in
`apps/api/.env.example`. For the web and optional mobile app it creates
`.env.local`. Existing local env files are preserved. The script
can be rerun safely and works without `apps/mobile`. A mobile app template
can consume the identity options by using the markers in its config or env
example. Run `./scripts/test-customize.sh` to exercise both layouts on fixtures.

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
| `WEB_LEGAL_APP_NAME` | `Full-stack starter` in the shell and `[App name]` in the legal templates | Name shown in the header, landing page, page metadata, and public policy and deletion templates. |
| `WEB_LEGAL_DOMAIN` | `[Site domain]` placeholder | Domain shown in the privacy and terms templates. |
| `WEB_SUPPORT_EMAIL` | Unset | Monitored mailbox for deletion requests sent from `/account-deletion`. |
| `ANDROID_PACKAGE_NAME` | Unset | Android application ID, for example `com.example.app`. |
| `ANDROID_SHA256_CERT_FINGERPRINTS` | Unset | Comma-separated, colon-delimited SHA-256 signing certificate fingerprints. Include the Play App Signing certificate for Play builds. |
| `IOS_TEAM_ID` | Unset | 10-character Apple Developer Team ID. |
| `IOS_BUNDLE_ID` | Unset | iOS bundle identifier, for example `com.example.app`. |
| `IOS_APPLINK_PATHS` | `/app/*` | Comma-separated URL paths beginning with `/`. Supports `*` for any number of characters and `?` for one character. Include the email-verification, password-reset and invite paths that the mobile app handles. The root path and any pattern matching `/privacy`, `/terms` or `/account-deletion` are rejected. |

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

| Variable | Default | Notes |
| --- | --- | --- |
| `APP_VARIANT` | `development` for local Expo CLI; **required** under EAS | `development` / `preview` / `production`. Under EAS CLI or on an EAS Build worker there is no default, and on a worker it must match a profile named after a variant. Non-production variants get `.dev` / `.preview` id suffixes, `-dev` / `-preview` scheme suffixes and a name suffix, so they install side by side. Also selects the runtime version (`1.0.0-<variant>`). |
| `API_URL` | `http://localhost:8000` (development only) | Required and `https://` for `preview` and `production`. No credentials, query string or fragment. Exposed to the app as `extra.apiUrl`; not used yet (no API calls). |
| `APP_NAME` / `APP_SLUG` | `Boilerplate` / `fullstack-boilerplate` | Display name; EAS project slug. |
| `ANDROID_PACKAGE` | `com.example.boilerplate`; **required** for production | Java package rules (letters, digits, `_`). Production rejects the `com.example` placeholder (Google Play does too). It can't change after the first Play release. |
| `IOS_BUNDLE_ID` | `com.example.boilerplate`; **required** for production | Letters, digits, `-` (no `_`). Same production rules. |
| `APP_SCHEME` | `boilerplate` | Deep-link scheme (before the variant suffix). |
| `APP_DOMAIN` | unset | Bare host for App Links / universal links, e.g. `app.example.com`. Has no effect without `APP_LINK_PATHS`. Use different hosts for preview and production. |
| `APP_LINK_PATHS` | unset | Explicit opt-in: comma-separated paths the app claims on `APP_DOMAIN`. `/verify-email` matches exactly, `/invite/` matches whole segments below it. No wildcards; `/privacy`, `/terms`, `/account-deletion` and `/.well-known` are always refused. Adds the Android `autoVerify` intent filter and the iOS `applinks:` domain. The web app's `IOS_APPLINK_PATHS` (AASA globs) must cover the same paths: `/verify-email` there for `/verify-email` here, `/invite/*` for `/invite/`. Its `ANDROID_PACKAGE_NAME` is the installed package, including the variant suffix. |
| `EAS_PROJECT_ID` / `EXPO_OWNER` | unset | From `eas init`. The project id also sets the EAS Update URL. |
| `SENTRY_DSN` | unset | Read into `extra.sentryDsn`; Sentry is not wired up yet. |

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
[`security.yml`](.github/workflows/security.yml) · [ADR 0005](docs/adr/0005-security-checks.md)

| Check | Coverage and failure condition |
| --- | --- |
| Gitleaks | Scans PR commits from the base SHA to the head SHA. On `main` pushes and the weekly run, scans the full fetched history across branches and tags. Reports matches with secret values redacted. |
| GitHub Dependency Review | Runs on PRs and fails on newly introduced known vulnerabilities at low severity or higher in the dependency graph. Requires the repository's **Dependency graph** setting. |
| pip-audit | Exports exact versions and hashes from `apps/api/uv.lock`, including development groups. Fails on known vulnerabilities reported for the export by the advisory service. |
| pnpm audit | Audits the workspace lockfile's production dependencies and fails on high or critical advisories. |

The current API lockfile includes `python-jose`
and `ecdsa` advisories without fixes at the time this check was added. The
Python audit reports them as failures.

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
request transactions. CI applies migrations to its Postgres 16 service, runs
`alembic check` for schema drift and runs the same suite. Plain pytest, `make test`
and CI share the 96.0% branch-aware coverage gate in `apps/api/pyproject.toml`,
with greenlet and thread tracing enabled.

Mobile unit tests (Jest + React Native Testing Library, no device needed):
`make test-mobile`. They cover the design tokens (including WCAG AA contrast), the secure
token storage wrapper, the persisted query cache, network status and the offline banner,
the app config validation, the Android manifest that `expo prebuild` would generate, and
routing tests that render the real `src/app` tree.

## Mobile

`apps/mobile` is an Expo SDK 58 app. This is the foundation only: screens are
placeholders, and nothing calls the API yet. Auth, the generated API client and real
data arrive in later phases.

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
    _layout.tsx            providers, theme, offline banner, root stack
    index.tsx              redirects to /sign-in (no session handling yet)
    (auth)/                sign-in, sign-up (stack with headers)
    (app)/                 items, settings (bottom tabs)
  src/components/          Screen, KeyboardAvoidingForm, TextField, Button, NetworkBanner
  src/theme/               design tokens + useTheme (ADR 0006)
  src/lib/                 runtime env, query client, network status, token storage,
                           API client headers
```

### What the foundation provides

- **Safe areas and edge-to-edge.** Expo SDK 54+ apps are always edge-to-edge on Android
  (and Android 15+ enforces it for apps targeting API 35), so content draws behind the
  system bars. `Screen` pads with safe-area insets per edge; headers and the tab bar pad
  their own edges. The status bar icons follow the theme.
- **Android back button.** In the tabs, back returns to the first tab, then leaves the
  app (`backBehavior="initialRoute"`). "Preview app screens" uses `router.replace`, so
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
  startup. Sign-out (phase 9b) calls `useClearQueryCache()`: it stops the scope's writes
  (including throttled writes still queued), waits for writes in flight, then clears
  memory and deletes the entry, so nothing can recreate it. Queries pause offline and
  resume on reconnect; returning to the foreground refetches and re-checks
  connectivity.
- **Offline banner.** Shown when NetInfo reports no connection or no internet access.
  It is an accessibility alert and a polite live region (announced on Android when it
  appears), and it takes over the top safe-area inset while visible.
- **Token storage** (`src/lib/token-storage.ts`): typed wrapper over `expo-secure-store`
  (Keychain / Keystore, `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`). The session (access +
  refresh token) is one entry, so a failed write never leaves a mixed pair. Nothing
  stores tokens yet.
- **Android release hardening.** Android Auto Backup is off (`allowBackup: false`), and
  permissions the app doesn't use (`SYSTEM_ALERT_WINDOW`, `VIBRATE`, legacy external
  storage) are removed from the merged manifest (`blockedPermissions`). A test checks the
  manifest that `expo prebuild` would generate for a production config.
- **API headers** (`src/lib/client-headers.ts`): builds `X-App-Version` / `X-Platform`
  values for the API's minimum-version check. Not sent yet.

### EAS builds and updates

| Profile | Purpose | Output | EAS environment | Update channel |
| --- | --- | --- | --- | --- |
| `development` | Development client (`expo-dev-client`), internal distribution | APK (Android) | `development` | none: a dev client loads JS from your dev server |
| `preview` | Internal testing build | APK, internal distribution | `preview` | `preview` |
| `production` | Store build | AAB (Android); `versionCode` / `buildNumber` auto-incremented by EAS | `production` | `production` |

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
environment, and it does so *before* it fetches EAS environment variables. Build workers
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
