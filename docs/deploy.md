# Deploying

Nothing in this repository has been deployed, and no cloud resource, token or
store account exists for it. The workflows below are written to skip with a
notice until you add the secrets, so a fresh clone stays green. Treat every
command here as untested against a real account until you have run it once on
staging.

| Piece | Default target | Workflow |
| --- | --- | --- |
| API (and, once it exists, the worker) | Fly.io, one app, process groups | `.github/workflows/deploy.yml` (`api` job), `apps/api/fly.toml` |
| Database | Neon Postgres | none; optional per-PR branches in `neon-preview.yml` |
| Web | Vercel | `deploy.yml` (`web` job) |
| Mobile | EAS Build / EAS Update, Google Play internal testing | `.github/workflows/mobile-release.yml` |

## GitHub Environments

Create two Environments, `staging` and `production` (Settings → Environments).
On `production`, add required reviewers (and, if you like, restrict it to the
`main` branch) so a manual production run waits for approval. Put each secret and
variable on the Environment, not the repository, so staging and production can
differ.

| Name | Kind | Used by | Notes |
| --- | --- | --- | --- |
| `FLY_API_TOKEN` | secret | api | Deploy token for the Fly app (`fly tokens create deploy -a <app>`). |
| `FLY_APP` | variable | api | The Fly app name. |
| `API_URL` | variable | api, mobile | Public API origin. The deploy job probes `${API_URL}/ready` when it is set. The mobile release also reads it (https required for preview and production). |
| `VERCEL_TOKEN` | secret | web | |
| `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | variables | web | From `.vercel/project.json` after `vercel link`. |
| `EXPO_TOKEN` | secret | mobile | Expo access token. |
| `EAS_PROJECT_ID`, `EXPO_OWNER` | variables | mobile | From `eas init` (see the mobile README section on EAS). |
| `APP_NAME`, `APP_SLUG`, `ANDROID_PACKAGE`, `IOS_BUNDLE_ID`, `APP_SCHEME`, `APP_DOMAIN`, `APP_LINK_PATHS` | variables | mobile | Optional app settings read by `app.config.ts`. Production needs real `ANDROID_PACKAGE` and `IOS_BUNDLE_ID`. |
| `NEON_API_KEY` | secret (repository) | preview DBs | Pull-request workflows cannot read Environment secrets, so this one lives on the repository. |
| `NEON_PROJECT_ID` | variable (repository) | preview DBs | |

`deploy.yml` runs `staging` automatically after CI succeeds on a push to `main`,
and any environment from **Actions → Deploy → Run workflow**. The mobile release is
manual only; the `preview` profile uses `staging` and `production` uses `production`.

## API and worker on Fly.io

`apps/api/fly.toml` describes one Fly app. `[build]` targets the `runtime` stage of
`apps/api/Dockerfile` (non-root, no build tools). `[processes]` holds the `app`
group (uvicorn, health-checked on `/health`). The background-jobs worker is a
second process group in the same app, so it shares secrets and releases: add it as
`worker = "<command>"` when the worker entrypoint exists (the file has a commented
placeholder; it is not there yet). A worker group has no `http_service`.

`release_command = "alembic upgrade head"` runs in a temporary machine of the new
release, with the app's secrets, before traffic moves. If the migration fails the
deploy stops and the previous release keeps serving. Because old and new releases
overlap during a rolling deploy, write migrations that the previous release can
still run against (add before use, drop in a later release).

First-time setup (once per Fly app):

```bash
fly apps create <app>
fly secrets set --app <app> \
  DATABASE_URL='<app role, pooled>' \
  MIGRATION_DATABASE_URL='<owner role, direct>' \
  SECRET_KEY="$(openssl rand -hex 32)" \
  CORS_ORIGINS='["https://app.example.com"]' \
  TRUSTED_HOSTS='["api.example.com"]'    # see the README's API environment table for the full list
```

### Two database URLs: why

| Variable | Role | Neon endpoint | Used by |
| --- | --- | --- | --- |
| `DATABASE_URL` | the **application role**: a non-owner role with only the table privileges it needs | **pooled** (`-pooler` in the host) | the running API and worker |
| `MIGRATION_DATABASE_URL` | the **owner role** that created the tables | **direct** | `alembic` in `release_command` (the API falls back to `DATABASE_URL` only when this is unset) |

Row-Level Security does not apply to a table's owner (unless forced) or to
superusers, so a policy-protected table must be queried by a role that does not own
it. The workspaces phase adds RLS; this split is how a deployment gets a non-owner
application role while migrations can still create and alter tables. On the first
deploy create the application role and grant it access (`GRANT SELECT, INSERT,
UPDATE, DELETE ON ALL TABLES IN SCHEMA public`, plus default privileges for tables
the owner creates later). Until RLS exists, nothing in the code requires the split,
but set it up now so staging matches production.

### Neon: pooled and direct

Neon exposes two hostnames per branch: the direct one, and a pooled one (PgBouncer in
transaction mode, `-pooler` in the host). Use the pooled URL for the application: many
short-lived connections are cheap. Use the direct URL for migrations and anything that
needs session state (advisory locks, `LISTEN`, `SET` that must persist). The API
disables psycopg's prepared statements (`prepare_threshold=None`), which is what
transaction pooling requires. Keep `sslmode=require` in both URLs.

Optional preview databases: `neon-preview.yml` creates the Neon branch
`preview/pr-<number>` for each pull request, applies the PR's migrations to it over
the direct URL and deletes the branch when the PR closes. It only creates a database;
it does not deploy an API or web for the PR. It never prints the connection strings.

### Notes for Google Cloud Run

Not automated here. The same image works (`--target runtime`, listens on 8000: set
`--port 8000`). Differences from Fly: run migrations as a separate Cloud Run **job**
using the owner URL (`MIGRATION_DATABASE_URL`) before routing traffic, since Cloud Run
has no `release_command`; run the worker as a second service (or job) with CPU always
allocated and no ingress; put both database URLs in Secret Manager; point Cloud Run's
startup probe at `/health` and keep `/ready` for monitoring. Cloud Run scales to zero
and can open many connections, so keep the pooled Neon URL for the app.

## Web

`deploy.yml` builds with Vercel's CLI (pinned, `pnpm dlx vercel@65.16.0`) and uploads the
prebuilt output: staging as a preview deployment, production with `--prod`. In the
Vercel project set the root directory to `apps/web`, enable "include source files outside
of the root directory" (the workspace lockfile and `packages/` live at the repo root), and
define `NEXT_PUBLIC_API_URL` (inlined at build time) and the `WEB_*` variables from the
README's web table for each Vercel environment.

Cloudflare Pages is an alternative, not wired up: Next.js on Cloudflare needs the
OpenNext adapter and its own build command, and `apps/web` has not been run that way.
The Docker image (`apps/web/Dockerfile`) also runs on any container host.

## Mobile release

`mobile-release.yml` is `workflow_dispatch` only and skips with a notice without
`EXPO_TOKEN`. It uses the repo's pinned `eas-cli` through `pnpm exec eas` (version in
the root `package.json`, mirrored by `cli.version` in `apps/mobile/eas.json`).

- **action = build**, profile `preview` or `production`: `eas build --platform android
  --non-interactive`. With **submit** (production only) it adds `--auto-submit`, which
  submits the AAB with the `production` profile in `eas.json` to the Play **internal**
  track. The Play service account key must already be uploaded to EAS
  (`pnpm exec eas credentials`); the first upload of an app to Play must be done by hand
  in the Play Console.
- **action = update**: `pnpm release:update <profile> --message ...`, the same
  guarded script described in the mobile section of the README. It refuses to publish
  unless the hosted EAS environment defines the matching variant and API URL.

The runner evaluates `app.config.ts` from the Environment's variables (EAS CLI does not
read `.env`); keep them equal to the variables of the EAS environment with the same name.

## Required status check

In branch protection for `main`, require the single check **CI / CI gate**. It is
produced by `ci.yml`, always runs, passes when path filtering skipped a job and fails
when any job failed or was cancelled. `Security` and `Pre-commit` are separate workflows
that always run; require them as well if you want them blocking.
