# Full-Stack Boilerplate

A starter monorepo with a **FastAPI** backend (`apps/api`), a **Next.js 15** frontend
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
  mobile/         Expo (React Native) app (pnpm workspace package "mobile")
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
- No Google sign-in button and no web tests yet.

**Mobile (`apps/mobile`)**: foundation only; see [Mobile](#mobile). It does not call
the API yet: no sign-in, no data.
- Expo SDK 58, React Native 0.88, TypeScript 6 (`strict` plus the shared
  `packages/config` options), Expo Router with `(auth)` and `(app)` route groups and
  placeholder screens (sign in, sign up, items, settings) in a tab layout.
- Styling with React Native `StyleSheet` and typed light/dark design tokens
  ([ADR 0005](docs/adr/0005-mobile-styling.md)).
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
  - **api**: `uv sync --locked`, ruff check, ruff format --check, mypy (not strict mode),
    pytest with a coverage report (no threshold);
  - **web**: `pnpm install --frozen-lockfile`, Prettier check, then ESLint, `tsc` and
    `next build` via Turborepo (ESLint and `tsc` run for every JS package, including
    mobile);
  - **scripts**: `scripts/test-customize.sh`, `scripts/test-check-containers.sh`;
  - **docker**: `scripts/test-dockerignore.sh`, build all images, then start postgres,
    api and web as packaged (`docker-compose.smoke.yml`: no source mounts), require all
    to be healthy, and run `scripts/check-containers.sh` (effective UID not 0, no
    mounts). Locally: `make smoke`;
  - **mobile** (`mobile.yml`, only when `apps/mobile`, `packages`, the lockfile or root
    JS config change): Prettier check, `tsc`, ESLint, Jest and `expo-doctor`.
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

## Upgrading an existing checkout

One-time steps when updating a checkout or deployment from before the monorepo layout
(Phase 2):

1. **Compose: the `client` service is now `web`.** A container from the old `client`
   service is left running as an orphan and keeps port 3000, so `web` fails with
   `port is already allocated`. Remove it once, keeping the database volume:

   ```bash
   docker compose up -d --build --remove-orphans
   ```

   (`--remove-orphans` only removes containers of services that no longer exist. It does
   not touch volumes, so the Postgres data in `postgres_data` is kept. Don't add `-v`.)

2. **Database URLs: the driver is now psycopg 3.** `psycopg2` is no longer installed. A
   `DATABASE_URL` with an explicit `postgresql+psycopg2://` prefix (in `.env` files,
   compose overrides, CI or deployment secrets) now fails at startup and in Alembic with
   `No module named 'psycopg2'`. Change the prefix to `postgresql+psycopg://`, or use
   plain `postgresql://`, which selects psycopg 3. Plain `postgresql://` URLs need no
   change.

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
make test                       # API tests (SQLite in memory; startup hook needs Postgres)
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

**Mobile** (`apps/mobile/.env` for local runs; template with comments in
`apps/mobile/.env.example`). Read by `app.config.ts` at build time and validated there:
an invalid value fails `expo start`, `expo-doctor` and EAS builds. Every value is
embedded in the app and readable by its users, so none of them may be secret.

| Variable | Default | Notes |
| --- | --- | --- |
| `APP_VARIANT` | `development` | `development` / `preview` / `production`. Set per profile in `eas.json`. Non-production variants get `.dev` / `.preview` id suffixes, `-dev` / `-preview` scheme suffixes and a name suffix, so they install side by side. |
| `API_URL` | `http://localhost:8000` (development only) | Required and `https://` for `preview` and `production`. Exposed to the app as `extra.apiUrl`; not used yet (no API calls). |
| `APP_NAME` / `APP_SLUG` | `Boilerplate` / `fullstack-boilerplate` | Display name; EAS project slug. |
| `ANDROID_PACKAGE` / `IOS_BUNDLE_ID` | `com.example.boilerplate` | Reverse-DNS ids (before the variant suffix). |
| `APP_SCHEME` | `boilerplate` | Deep-link scheme (before the variant suffix). |
| `APP_DOMAIN` | unset | Bare host, e.g. `app.example.com`. Adds Android App Links intent filters (`autoVerify`, paths `/verify-email`, `/reset-password`, `/invite`) and the iOS `applinks:` associated domain. Unset: neither is added. |
| `EAS_PROJECT_ID` / `EXPO_OWNER` | unset | From `eas init`. The project id also sets the EAS Update URL. |
| `SENTRY_DSN` | unset | Read into `extra.sentryDsn`; Sentry is not wired up yet. |

## Common commands

```bash
make help                      # list all targets
make setup                     # install locked Python + JS dependencies
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
make migrate                   # alembic upgrade head (no migrations exist yet)
make migration name=add_column # autogenerate a migration
make db-shell                  # psql into the dev database
make fresh                     # wipe the DB volume, rebuild, start
make smoke                     # build + start all images as packaged; healthy, non-root, no mounts
```

## Testing

```bash
docker compose up -d postgres
make test
```

API tests use an in-memory SQLite database through a dependency override
(`apps/api/tests/conftest.py`), so they do **not** exercise Postgres or the psycopg 3
driver. The app's startup hook still runs `create_all()` against `DATABASE_URL`, so a
reachable Postgres is required (CI provides one for that reason only). Moving the suite
to Postgres is planned for the next phase. There are no web tests yet.

Mobile unit tests (Jest + React Native Testing Library, no device needed):
`make test-mobile`. They cover the design tokens (including WCAG AA contrast), the secure
token storage wrapper, the network banner, the app config validation, and a routing smoke
test that renders the real `src/app` tree.

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
# or in the cloud: npx eas-cli@latest build --profile development --platform android
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
  src/theme/               design tokens + useTheme (ADR 0005)
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
  (hardware back, header back, iOS swipe) asks for confirmation (`usePreventRemove`).
  Android's predictive back gesture is off (`predictiveBackGestureEnabled: false`).
- **Keyboard.** `KeyboardAvoidingForm` uses `behavior="padding"` on both platforms
  (Android windows no longer resize for the keyboard under edge-to-edge) and offsets by
  the header height.
- **Accessibility.** Inputs are labelled, buttons have roles and disabled state, screen
  titles are headers, tabs have accessibility labels, buttons and inputs are at least
  48 dp tall, and the color pairs the components use meet WCAG AA contrast in light and
  dark (tested).
- **Data layer scaffold.** TanStack Query with its cache persisted to AsyncStorage
  (24 h max age; discarded when the app version changes). AsyncStorage is not
  encrypted: queries with sensitive data must set `meta: { persist: false }`. Query
  refetching pauses offline and resumes on reconnect / app foreground.
- **Offline banner.** Shown when NetInfo reports no connection or no internet access.
  It is an accessibility alert and a polite live region (announced on Android when it
  appears), and it takes over the top safe-area inset while visible.
- **Token storage** (`src/lib/token-storage.ts`): typed wrapper over `expo-secure-store`
  (Keychain / Keystore, `AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY`). Nothing stores tokens yet.
- **API headers** (`src/lib/client-headers.ts`): builds `X-App-Version` / `X-Platform`
  values for the API's minimum-version check. Not sent yet.

### EAS profiles

| Profile | Purpose | Output | Update channel |
| --- | --- | --- | --- |
| `development` | Development client (`expo-dev-client`), internal distribution | APK (Android) | none: a dev client loads JS from your dev server |
| `preview` | Internal testing build | APK, internal distribution | `preview` |
| `production` | Store build | AAB (Android); `versionCode` / `buildNumber` auto-incremented by EAS | `production` |

- Build numbers are managed by EAS (`cli.appVersionSource: "remote"`). The user-facing
  version is `APP_VERSION` in `app.config.ts`. `runtimeVersion` uses the `appVersion`
  policy, so an update only reaches binaries with the same version.
- `eas.json` pins EAS's Node (26.13.1) and pnpm (12.23.0) to match the repo.
- `preview` and `production` builds fail at config time unless `API_URL` (https) is
  set, e.g. as an EAS environment variable.

First-time setup (needs an Expo account; none of this has been run for this repo):

```bash
cd apps/mobile
npx eas-cli@latest login
npx eas-cli@latest init                 # creates the EAS project; put its id in EAS_PROJECT_ID
npx eas-cli@latest env:create           # API_URL, APP_DOMAIN, EAS_PROJECT_ID, ... per environment
npx eas-cli@latest build --profile preview --platform android
npx eas-cli@latest update --channel preview --environment preview --message "..."
```

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
