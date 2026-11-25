import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import LOCAL_SECRET, TEST_SECRET, DatabaseSettings, Settings

TEST_SETTINGS = {
    "env": "test",
    "secret_key": secrets.token_hex(32),
    "database_url": "postgresql://postgres:postgres@localhost/test_db",
}
KNOWN_SECRETS = [
    LOCAL_SECRET,
    TEST_SECRET,
    f"{LOCAL_SECRET}\n",
    f"  {TEST_SECRET} ",
]
# The minimum that staging and production accept.
DEPLOYED = {
    "secret_key": "staging-fixture-" * 3,
    "jwt_secret_key": "jwt-staging-fixture-" * 3,
    "database_url": "postgresql://app:app@pooler.example/db",
    "email_backend": "smtp",
    "smtp_security": "starttls",
    "web_url": "https://web.example",
}


@pytest.mark.parametrize("env", ["test", "staging", "production"])
@pytest.mark.parametrize("secret", [None, "", "too-short", " " * 32, *KNOWN_SECRETS])
def test_requires_secret_outside_local_environments(monkeypatch, env, secret):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(env=env, secret_key=secret, _env_file=None)


@pytest.mark.parametrize("env_name", [None, "production", "test"])
def test_boot_fails_without_secret(database_url, tmp_path, env_name):
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
    monkeypatch.setenv("JWT_SECRET_KEY", "jwt-staging-fixture-" * 3)
    monkeypatch.setenv("WEB_URL", "https://web.example")
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")
    monkeypatch.setenv("SMTP_HOST", "smtp.example")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_SECURITY", "starttls")
    monkeypatch.setenv("GOOGLE_AUTH_ENABLED", "true")
    monkeypatch.setenv("GOOGLE_ANDROID_CLIENT_ID", "123-abc.apps.googleusercontent.com")
    config = Settings(_env_file=None)
    assert config.database().host == "pooler.example"
    assert DatabaseSettings(_env_file=None).database(migration=True).host == "direct.example"
    assert config.cors_origins == ["https://web.example"]
    assert config.trusted_hosts == ["api.example"]
    assert config.max_request_body_bytes == 256
    assert config.web_url.host == "web.example"
    assert config.signing_key == "staging-fixture-" * 3
    assert config.jwt_key == "jwt-staging-fixture-" * 3
    assert (config.smtp_host, config.smtp_port, config.smtp_security) == (
        "smtp.example",
        587,
        "starttls",
    )
    assert config.google_client_ids == ["123-abc.apps.googleusercontent.com"]
    assert config.secure_cookies is True


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"env": "wrong"}, "development"),
        ({"database_url": "sqlite://"}, "PostgreSQL"),
        ({"database_url": "not-a-db-url"}, "Invalid PostgreSQL database URL"),
        ({"trusted_hosts": ["a*"]}, "Trusted host wildcards"),
        ({"migration_database_url": "postgresql+psycopg2://localhost/db"}, "psycopg 3"),
        ({"google_auth_enabled": True}, "GOOGLE_AUTH_ENABLED requires"),
        ({"google_web_client_id": "example"}, "apps.googleusercontent.com"),
        ({"smtp_username": "mailer"}, "SMTP_USERNAME and SMTP_PASSWORD"),
        ({"max_request_body_bytes": 0}, "greater than 0"),
        ({"access_token_expire_minutes": 61}, "less than or equal to 60"),
        ({"jwt_algorithm": "RS256"}, "jwt_algorithm"),
        ({**DEPLOYED, "env": "production", "database_url": None}, "database URL is required"),
        ({"database_url": None}, "database URL is required"),
    ],
)
def test_rejects_misconfigured_settings(fields, message):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **{**TEST_SETTINGS, **fields})


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
        Settings(cors_origins=[origin], _env_file=None, **TEST_SETTINGS)


def test_lowercases_explicit_cors_origins():
    origins = ["HTTPS://Web.Example.com", "http://LOCALHOST:3000", "http://[::AF]:3000"]
    settings = Settings(cors_origins=origins, _env_file=None, **TEST_SETTINGS)
    assert settings.cors_origins == [
        "https://web.example.com",
        "http://localhost:3000",
        "http://[::af]:3000",
    ]


@pytest.mark.parametrize("env", ["staging", "production"])
def test_rejects_catch_all_trusted_host(env):
    fields = {"env": env, **DEPLOYED}
    with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
        Settings(trusted_hosts=["api.example.com", "*"], _env_file=None, **fields)
    assert Settings(trusted_hosts=["*.example.com"], _env_file=None, **fields).trusted_hosts == [
        "*.example.com"
    ]


@pytest.mark.parametrize("env", ["staging", "production"])
@pytest.mark.parametrize(
    ("jwt_secret", "message"),
    [
        (None, "JWT_SECRET_KEY must be a unique secret of at least 32 bytes"),
        ("", "at least 32 bytes"),
        ("x" * 31, "at least 32 bytes"),
        (" " * 40, "at least 32 bytes"),
        (LOCAL_SECRET + "-padding-padding", None),
        (TEST_SECRET, "at least 32 bytes"),
        ("staging-fixture-" * 3, "must differ from SECRET_KEY"),
    ],
)
def test_deployed_environments_require_a_distinct_jwt_secret(env, jwt_secret, message):
    fields = {**DEPLOYED, "env": env, "jwt_secret_key": jwt_secret}
    if message is None:
        assert Settings(_env_file=None, **fields).jwt_key == jwt_secret
        return
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **fields)


def test_jwt_key_length_follows_the_algorithm():
    fields = {**DEPLOYED, "env": "production", "jwt_algorithm": "HS512"}
    with pytest.raises(ValidationError, match="at least 64 bytes for HS512"):
        Settings(_env_file=None, **fields)
    assert (
        Settings(_env_file=None, **{**fields, "jwt_secret_key": "k" * 64}).jwt_algorithm == "HS512"
    )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("email_backend", "console", "EMAIL_BACKEND must be smtp"),
        ("email_backend", "memory", "EMAIL_BACKEND must be smtp"),
        ("rate_limit_backend", "memory", "RATE_LIMIT_BACKEND must be postgres"),
        ("web_url", "http://web.example", "WEB_URL must use https"),
    ],
)
def test_deployed_environments_reject_local_only_backends(field, value, message):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **{**DEPLOYED, "env": "production", field: value})


def test_local_environments_derive_a_jwt_key_and_allow_local_backends(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    development = Settings(env="development", _env_file=None)
    assert development.database().host == "localhost"
    assert development.signing_key == LOCAL_SECRET
    assert development.jwt_key not in {LOCAL_SECRET, ""}
    assert development.secure_cookies is False
    test = Settings(
        _env_file=None, **TEST_SETTINGS, email_backend="memory", rate_limit_backend="memory"
    )
    assert test.jwt_key != development.jwt_key
    assert test.secure_cookies is True


def test_google_client_ids():
    config = Settings(
        _env_file=None,
        **TEST_SETTINGS,
        google_auth_enabled=True,
        google_web_client_id="1-web.apps.googleusercontent.com",
        google_ios_client_id="1-ios.apps.googleusercontent.com",
    )
    assert config.google_client_ids == [
        "1-web.apps.googleusercontent.com",
        "1-ios.apps.googleusercontent.com",
    ]


def test_boot_fails_without_jwt_secret_in_production(database_url, tmp_path):
    env = {
        **{k: v for k, v in os.environ.items() if k not in {"JWT_SECRET_KEY", "ENV"}},
        "ENV": "production",
        "SECRET_KEY": "production-fixture-" * 3,
        "DATABASE_URL": database_url.render_as_string(hide_password=False),
        "EMAIL_BACKEND": "smtp",
        "WEB_URL": "https://web.example",
        "PYTHONPATH": os.getcwd(),
    }
    process = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert "JWT_SECRET_KEY" in process.stderr


def test_env_example_is_a_valid_development_configuration(monkeypatch, tmp_path):
    for name in ("ENV", "SECRET_KEY", "DATABASE_URL", "JWT_SECRET_KEY"):
        monkeypatch.delenv(name, raising=False)
    example = Path(__file__).resolve().parents[1] / ".env.example"
    env_file = tmp_path / ".env"
    env_file.write_text(example.read_text().replace("{{GENERATE_SECRET_KEY}}", "x" * 64))
    config = Settings(_env_file=env_file)
    assert config.env == "development"
    assert config.access_token_expire_minutes == 15
    assert config.email_backend == "console"
    assert config.google_auth_enabled is False
    assert config.jwt_secret_key is not None and config.jwt_key != config.signing_key


@pytest.mark.parametrize("env", ["test", "staging", "production"])
@pytest.mark.parametrize("jwt_secret", KNOWN_SECRETS)
def test_known_jwt_secrets_are_rejected_outside_development(env, jwt_secret):
    fields = {**DEPLOYED, **({} if env != "test" else TEST_SETTINGS), "env": env}
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY must be a unique secret"):
        Settings(_env_file=None, **{**fields, "jwt_secret_key": jwt_secret})


def test_padded_copies_of_the_signing_key_are_not_distinct():
    secret = DEPLOYED["secret_key"]
    with pytest.raises(ValidationError, match="must differ from SECRET_KEY"):
        Settings(
            _env_file=None, **{**DEPLOYED, "env": "production", "jwt_secret_key": f" {secret}\n"}
        )


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        ("https://web.example:443", "https://web.example"),
        ("HTTP://Web.Example:80", "http://web.example"),
        ("http://web.example:8080", "http://web.example:8080"),
        ("https://web.example:80", "https://web.example:80"),
        ("http://[::1]:80", "http://[::1]"),
    ],
)
def test_cors_origins_drop_default_ports(configured, expected):
    # Browsers omit default ports from the Origin header, so keep the comparable form.
    assert Settings(_env_file=None, **TEST_SETTINGS, cors_origins=[configured]).cors_origins == [
        expected
    ]


def test_smtp_credentials_are_never_sent_without_tls():
    credentials = {"smtp_username": "mailer", "smtp_password": "s3cret"}
    with pytest.raises(ValidationError, match="SMTP credentials require"):
        Settings(_env_file=None, **TEST_SETTINGS, **credentials)
    for security in ("starttls", "tls"):
        Settings(_env_file=None, **TEST_SETTINGS, **credentials, smtp_security=security)
    with pytest.raises(ValidationError, match="SMTP credentials require"):
        Settings(
            _env_file=None,
            **{**DEPLOYED, "env": "production", "smtp_security": "none"},
            **credentials,
            smtp_allow_insecure=True,
        )


@pytest.mark.parametrize("env", ["staging", "production"])
def test_deployed_smtp_requires_tls_unless_a_local_relay_is_allowed(env):
    fields = {**DEPLOYED, "env": env, "smtp_security": "none"}
    with pytest.raises(ValidationError, match="SMTP_SECURITY must be starttls or tls"):
        Settings(_env_file=None, **fields)
    assert Settings(_env_file=None, **fields, smtp_allow_insecure=True).smtp_allow_insecure


def test_missing_test_secret_is_explained(database_url):
    env = {name: value for name, value in os.environ.items() if name != "SECRET_KEY"}
    env.update(ENV="test", DATABASE_URL=database_url.render_as_string(hide_password=False))
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--no-cov",
            "tests/test_routers/test_health.py",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert process.returncode != 0
    assert "Set SECRET_KEY to a random test secret" in process.stdout
