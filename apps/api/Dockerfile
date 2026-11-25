# syntax=docker/dockerfile:1
#
# Targets:
#   runtime (default) - slim production image: no build tools, no uv, non-root.
#   dev               - adds the dev dependency group (pytest, ruff, mypy) and
#                       runs uvicorn with --reload; used by docker-compose.yml.

ARG PYTHON_IMAGE=python:3.13.18-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.9

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # The virtualenv lives outside /app so a dev bind mount of the source
    # doesn't hide it.
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app
EXPOSE 8000
# Stdlib-only probe: healthy only on a 2xx from /health (no redirects), 2s timeout.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "/app/healthcheck.py"]

# ---------------------------------------------------------------------------
FROM base AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# Application files with normalized permissions (readable by everyone, writable
# by root only), regardless of the host checkout's file modes (e.g. 600 under a
# restrictive umask). Only what the app needs at runtime: no tests.
FROM base AS app-files
COPY alembic.ini healthcheck.py /src/
COPY alembic /src/alembic
COPY app /src/app
RUN chmod -R u=rwX,go=rX /src

FROM builder AS dev-builder
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# ---------------------------------------------------------------------------
FROM base AS dev
COPY --from=dev-builder /opt/venv /opt/venv
COPY . .
# Runs as root on purpose: the source is bind-mounted from the host in
# development and tools write caches/reports into it. Never deploy this target.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--reload"]

# ---------------------------------------------------------------------------
FROM base AS runtime
ENV ENV=production
# pip ships with the base image but is never needed at runtime.
RUN python -m pip uninstall --yes --quiet pip \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
# Root-owned and read-only for the app user.
COPY --from=app-files /src/ ./
USER app:app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
