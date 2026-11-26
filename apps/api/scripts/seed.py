"""Seed local development data: a verified demo user, a workspace and a few items.

Run with ``make seed`` (inside the api container). Idempotent: re-running keeps the same
user and workspace and only adds items when the workspace has none. The user is inserted
with the owner connection (``MIGRATION_DATABASE_URL``); the workspace and items are
created through the real API, so row-level security and validation apply. Refuses to run
outside ENV=development.
"""

import json
import os
import urllib.error
import urllib.request
from datetime import UTC, datetime

from sqlalchemy import create_engine, text

from app.core.config import postgres_url
from app.core.security import _hash  # synchronous argon2id hash

EMAIL = "demo@example.com"
PASSWORD = "demo-password-123"
API_URL = os.environ.get("SEED_API_URL", "http://localhost:8000")
ITEMS = ["Try the web app", "Try the mobile app", "Invite someone to this workspace"]


def call(method: str, path: str, body: object | None = None, token: str | None = None) -> object:
    headers = {"Content-Type": "application/json", "X-Platform": "other"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        API_URL + path,
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        raise SystemExit(
            f"{method} {path} -> {error.code}: {error.read().decode()[:300]}"
        ) from None
    return json.loads(raw) if raw else None


def ensure_user() -> None:
    url = os.environ.get("MIGRATION_DATABASE_URL") or os.environ["DATABASE_URL"]
    engine = create_engine(postgres_url(url))
    with engine.begin() as connection:
        found = connection.execute(
            text("SELECT 1 FROM users WHERE lower(email) = :email"), {"email": EMAIL}
        ).first()
        if found is None:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, name, hashed_password, is_active, email_verified_at,"
                    " created_at, updated_at) VALUES (gen_random_uuid(), :email, 'Demo User', :hash,"
                    " true, :now, :now, :now)"
                ),
                {"email": EMAIL, "hash": _hash(PASSWORD), "now": datetime.now(UTC)},
            )
    engine.dispose()


def main() -> None:
    if os.environ.get("ENV", "production") != "development":
        raise SystemExit("seed only runs with ENV=development")
    ensure_user()
    tokens = call("POST", "/v1/auth/login", {"email": EMAIL, "password": PASSWORD})
    token = tokens["access_token"]  # type: ignore[index]
    page = call("GET", "/v1/workspaces", token=token)
    workspaces = page["items"]  # type: ignore[index]
    if workspaces:
        workspace = workspaces[0]
    else:
        workspace = call("POST", "/v1/workspaces", {"name": "Demo Workspace"}, token)
    workspace_id = workspace["id"]
    # Item routes take the workspace in a header; reuse call() with it by extending headers.
    existing = _items(token, workspace_id)
    if not existing:
        for title in ITEMS:
            _items(token, workspace_id, {"title": title})
    print(f"Seeded: sign in as {EMAIL} / {PASSWORD} (workspace {workspace_id})")


def _items(token: str, workspace_id: str, body: dict[str, str] | None = None) -> list[object]:
    request = urllib.request.Request(
        API_URL + "/v1/items",
        method="POST" if body else "GET",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "X-Workspace-Id": workspace_id,
            "X-Platform": "other",
        },
        data=json.dumps(body).encode() if body else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise SystemExit(f"items -> {error.code}: {error.read().decode()[:300]}") from None
    return payload.get("items", []) if isinstance(payload, dict) and "items" in payload else []


if __name__ == "__main__":
    main()
