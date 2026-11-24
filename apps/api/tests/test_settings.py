import os
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.core.config import LOCAL_SECRET, DatabaseSettings, Settings


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize("secret", [None, "", "too-short", " " * 32, LOCAL_SECRET])
def test_requires_secret_outside_local_environments(monkeypatch, env, secret):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(env=env, secret_key=secret, _env_file=None)


@pytest.mark.parametrize("env_name", [None, "production"])
def test_boot_fails_without_production_secret(database_url, tmp_path, env_name):
    env = {
        **os.environ,
        "DATABASE_URL": database_url.render_as_string(hide_password=False),
        "PYTHONPATH": os.getcwd(),
    }
    env.pop("SECRET_KEY", None)
    env.pop("ENV", None)
    if env_name is not None:
        env["ENV"] = env_name
    process = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert "SECRET_KEY" in process.stderr


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("ENV", "staging")
    monkeypatch.setenv("SECRET_KEY", "staging-fixture-" * 3)
    monkeypatch.setenv("DATABASE_URL", "postgresql://app:app@pooler.example/db")
    monkeypatch.setenv("MIGRATION_DATABASE_URL", "postgresql://owner:owner@direct.example/db")
    monkeypatch.setenv("CORS_ORIGINS", '["https://web.example"]')
    monkeypatch.setenv("TRUSTED_HOSTS", '["api.example"]')
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "256")
    monkeypatch.setenv("GOOGLE_REDIRECT_URI", "https://api.example/v1/auth/google/callback")
    monkeypatch.setenv("FRONTEND_URL", "https://web.example")
    config = Settings(_env_file=None)
    assert config.database().host == "pooler.example"
    assert DatabaseSettings(_env_file=None).database(migration=True).host == "direct.example"
    assert config.cors_origins == ["https://web.example"]
    assert config.trusted_hosts == ["api.example"]
    assert config.max_request_body_bytes == 256
    assert config.google_redirect_uri.path == "/v1/auth/google/callback"
    assert config.frontend_url.host == "web.example"
    assert config.signing_key == "staging-fixture-" * 3


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"env": "wrong"}, "development"),
        ({"database_url": "sqlite://"}, "PostgreSQL"),
        ({"database_url": "not-a-db-url"}, "Invalid PostgreSQL database URL"),
        ({"trusted_hosts": ["a*"]}, "Trusted host wildcards"),
        ({"migration_database_url": "postgresql+psycopg2://localhost/db"}, "psycopg 3"),
        ({"google_client_id": "example"}, "must be set together"),
        ({"max_request_body_bytes": 0}, "greater than 0"),
        (
            {"env": "production", "database_url": None, "secret_key": "a" * 32},
            "database URL is required",
        ),
    ],
)
def test_rejects_misconfigured_settings(fields, message):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **{"env": "test", **fields})


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.com",
        "example.com",
        "ftp://example.com",
        "https://",
        "https://example.com/",
        "https://example.com?",
        "https://example.com#fragment",
        "https://user:password@example.com",
        "https://example.com:invalid",
        "https://example.com:65536",
        "https://example.com\\path",
    ],
)
def test_rejects_invalid_cors_origins(origin):
    with pytest.raises(ValidationError, match="cors_origins"):
        Settings(env="test", cors_origins=[origin], _env_file=None)


def test_accepts_explicit_cors_origins():
    origins = ["https://web.example.com", "http://localhost:3000", "http://[::1]:3000"]
    assert Settings(env="test", cors_origins=origins, _env_file=None).cors_origins == origins


@pytest.mark.parametrize("env", ["staging", "production"])
def test_rejects_catch_all_trusted_host(env):
    fields = {
        "env": env,
        "secret_key": "staging-fixture-" * 3,
        "database_url": "postgresql://app:app@pooler.example/db",
    }
    with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
        Settings(trusted_hosts=["api.example.com", "*"], _env_file=None, **fields)
    assert Settings(trusted_hosts=["*.example.com"], _env_file=None, **fields).trusted_hosts == [
        "*.example.com"
    ]
