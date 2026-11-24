# 0001. Python tooling: uv

- Status: Accepted
- Date: 2026-11-24

## Context

The API used Poetry with caret version ranges and an unpinned `pip install poetry` in
its Dockerfile. Poetry was installed into the runtime interpreter, so build tooling (and
its dependencies such as `requests`) leaked into the production image. Installs were
slow, and the Poetry version was not reproducible.

## Decision

Use [uv](https://docs.astral.sh/uv/) for the API (`apps/api`):

- `pyproject.toml` uses standard PEP 621 `[project]` metadata with exact `==` pins for
  direct dependencies and a PEP 735 `dev` dependency group. `uv.lock` is committed.
- `[tool.uv] package = false`: the API is an application, so only dependencies are
  installed, not the project itself.
- The uv version is pinned (`required-version` in `pyproject.toml`, the CI action input,
  and the uv image tag in the Dockerfile). The Python minor version is pinned in
  `.python-version` and `requires-python`.
- Every install uses `--locked`, so a stale lockfile fails instead of being silently
  re-resolved.
- In Docker, uv exists only in the builder stages; the runtime image receives a
  ready-made virtualenv at `/opt/venv`.

## Consequences

- Reproducible installs in CI, Docker and on developer machines from one lockfile.
- Contributors need uv locally for host-side commands (`make setup`, `make test`).
- The project name is now a fixed, valid PEP 508 name (`api`). It is no longer a
  template placeholder for `scripts/customize.sh`: the placeholder was not a valid name,
  and a renamed project would no longer match `uv.lock`.
