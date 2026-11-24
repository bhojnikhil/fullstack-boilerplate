# 0003. Container images: multi-stage, slim, non-root

- Status: Accepted
- Date: 2026-11-24

## Context

The API image was single-stage: it included `build-essential`, `postgresql-client`,
Poetry and all dev dependencies, ran as root, and weighed about 1.24 GB. The web image
copied the full `node_modules` and ran `next start` as root.

## Decision

**API (`apps/api/Dockerfile`)**

- `builder` stage: copies the pinned uv binary and runs `uv sync --locked --no-dev` into
  `/opt/venv`.
- `runtime` stage (default): `python:<pinned>-slim` base, the venv, and only `app/`,
  `alembic/`, `alembic.ini` and `healthcheck.py`. No compilers, uv, Poetry, pip or tests.
  Runs as a dedicated unprivileged user (uid 10001). Code files are root-owned and
  read-only for that user. File permissions are normalized in a build stage, so restrictive
  host modes (e.g. `600`) don't break the image.
- `dev` stage: adds the dev dependency group and `--reload`. Used only by
  `docker-compose.yml` with the source bind-mounted, and runs as root for that reason.
  Never deploy it.
- The virtualenv lives outside `/app`, so the dev bind mount doesn't hide it.

**Web (`apps/web/Dockerfile`)**

- Next.js `output: "standalone"`. The runtime stage contains only the standalone server,
  static assets and `public/`, and runs as the image's unprivileged `node` user. pnpm and
  dev dependencies are build-stage only.
- `NEXT_PUBLIC_API_URL` is a build argument, because Next.js inlines it at build time.

**Both**: base images pinned to exact versions, and stdlib-only / `fetch`-based
`HEALTHCHECK`s that require a 2xx response and don't follow redirects. CI runs both
images as packaged (`docker-compose.smoke.yml`, no source mounts) and requires them to
become healthy and run as non-root.

## Consequences

- API image about 360 MB (from about 1.24 GB); web image about 345 MB.
- Running tests or migrations inside the runtime image is not possible by design. Use the
  `dev` target or run them on the host with uv.
- Base image digests are not pinned. Updating pinned tags needs a dependency-update bot
  (planned) or manual bumps.
