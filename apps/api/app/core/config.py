import hashlib
import hmac
import re
from typing import Literal, Self

from fastapi import Request
from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

Environment = Literal["development", "test", "staging", "production"]
DEFAULT_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/boilerplate"
LOCAL_SECRET = "dev-secret-key-change-in-production"
TEST_SECRET = "test-secret-key-do-not-use-in-production-12345678"
# Secrets published in this repository; rejected (after stripping) outside development.
PUBLISHED_SECRETS = frozenset({LOCAL_SECRET, TEST_SECRET})
MIN_SECRET_LENGTH = 32
ORIGIN_PATTERN = re.compile(
    r"https?://(?:[a-z0-9.-]+|\[[0-9a-f:.]+\])(?::[0-9]+)?", re.IGNORECASE | re.ASCII
)
GOOGLE_CLIENT_ID_PATTERN = re.compile(r"[A-Za-z0-9-]+\.apps\.googleusercontent\.com")
VERSION_PATTERN = re.compile(
    r"[0-9]{1,6}(?:\.[0-9]{1,6}){0,2}(?:[-+][0-9A-Za-z.+-]{1,32})?", re.ASCII
)
CONTENT_TYPE_PATTERN = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9.+-]{0,60}/[A-Za-z0-9][A-Za-z0-9.+-]{0,60}"
)
JwtAlgorithm = Literal["HS256", "HS384", "HS512"]


def postgres_url(value: str) -> URL:
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("Invalid PostgreSQL database URL") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("Database URLs must use PostgreSQL with psycopg 3")
    return url.set(drivername="postgresql+psycopg")


def without_default_port(origin: str) -> str:
    """Browsers omit default ports from Origin, so https://x:443 would never match."""
    for scheme, port in (("https://", ":443"), ("http://", ":80")):
        if origin.startswith(scheme) and origin.endswith(port):
            return origin.removesuffix(port)
    return origin


def secret_value(secret: SecretStr | None) -> str:
    """A configured secret, treating an empty environment variable as unset."""
    return secret.get_secret_value() if secret is not None else ""


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    env: Environment = "production"
    database_url: SecretStr | None = None
    migration_database_url: SecretStr | None = None

    def database(self, *, migration: bool = False) -> URL:
        configured = self.migration_database_url if migration else None
        if not configured or not configured.get_secret_value():
            configured = self.database_url
        if configured and configured.get_secret_value():
            return postgres_url(configured.get_secret_value())
        if self.env == "development":
            return postgres_url(DEFAULT_DATABASE_URL)
        raise ValueError("A database URL is required outside development")


class Settings(DatabaseSettings):
    app_name: str = Field(default="Boilerplate App", min_length=1, max_length=100)
    # Base URL of the web app. Links in emails point here (phase 8 adds the pages).
    web_url: HttpUrl = HttpUrl("http://localhost:3000")

    # Server-side HMAC root (IP hashes, CSRF tokens, rate-limit and audit identifiers).
    secret_key: SecretStr | None = None
    # Signs access tokens only. Separate from SECRET_KEY so either can be rotated alone.
    jwt_secret_key: SecretStr | None = None
    jwt_algorithm: JwtAlgorithm = "HS256"
    jwt_issuer: str = Field(default="boilerplate-api", min_length=1)
    jwt_audience: str = Field(default="boilerplate-api", min_length=1)
    access_token_expire_minutes: int = Field(default=15, gt=0, le=60)
    # A refresh token extends its session by this much (idle timeout) ...
    refresh_token_expire_days: int = Field(default=30, gt=0, le=365)
    # ... up to this absolute session lifetime, after which the user signs in again.
    session_max_age_days: int = Field(default=90, gt=0, le=730)
    # Account deletion, email changes and Google (un)linking need a sign-in this recent.
    reauthentication_max_age_minutes: int = Field(default=10, gt=0, le=60)

    # Optional k-anonymity lookup against Have I Been Pwned (only a SHA-1 prefix is sent).
    password_breach_check: bool = False
    email_token_expire_hours: int = Field(default=24, gt=0, le=168)
    password_reset_expire_minutes: int = Field(default=30, gt=0, le=1440)

    google_auth_enabled: bool = False
    google_web_client_id: str = ""
    google_android_client_id: str = ""
    google_ios_client_id: str = ""

    email_backend: Literal["console", "smtp", "resend", "memory"] = "console"
    email_from: str = Field(default="Boilerplate App <no-reply@localhost>", min_length=3)
    smtp_host: str = "localhost"
    smtp_port: int = Field(default=1025, gt=0, lt=65536)
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_security: Literal["none", "starttls", "tls"] = "none"
    # Staging and production require TLS; set this only for a relay on the same host or
    # private network (a sidecar). Credentials are never sent without TLS.
    smtp_allow_insecure: bool = False
    smtp_timeout_seconds: float = Field(default=10, gt=0, le=60)
    resend_api_key: SecretStr = SecretStr("")
    resend_timeout_seconds: float = Field(default=10, gt=0, le=60)

    # Background jobs (the worker process; see docs/adr/0011-postgres-job-queue.md).
    job_poll_interval_seconds: float = Field(default=2, gt=0, le=60)
    worker_concurrency: int = Field(default=4, ge=1, le=64)
    # A job claimed longer ago than this is presumed lost with its worker and is re-run.
    # Handlers are cancelled after JOB_TIMEOUT_SECONDS, which must be shorter.
    job_lock_timeout_seconds: int = Field(default=300, ge=30, le=3600)
    # Jobs older than this are deleted whatever their state, so payloads (which can hold
    # one-time links) do not accumulate.
    job_retention_days: int = Field(default=3, ge=1, le=90)
    job_timeout_seconds: int = Field(default=120, ge=5, le=3000)

    # Expo push notifications. "log" only logs counts (never tokens or message text).
    push_backend: Literal["expo", "log", "memory"] = "log"
    expo_access_token: SecretStr = SecretStr("")
    expo_push_timeout_seconds: float = Field(default=10, gt=0, le=60)

    # Object storage (S3-compatible: AWS S3, Cloudflare R2, MinIO). "disabled" by default.
    storage_backend: Literal["s3", "memory", "disabled"] = "disabled"
    storage_endpoint_url: HttpUrl | None = None
    storage_region: str = "auto"
    storage_bucket: str = ""
    storage_access_key_id: str = ""
    storage_secret_access_key: SecretStr = SecretStr("")
    storage_max_upload_bytes: int = Field(default=10_485_760, gt=0, le=5_368_709_120)
    storage_allowed_content_types: list[str] = [
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    ]
    storage_url_expire_seconds: int = Field(default=600, ge=30, le=3600)

    # Mobile version gate: GET /v1/meta, and 426 app_update_required below the minimum.
    min_supported_app_version: str = "0.0.0"
    latest_app_version: str = "1.0.0"

    # Error reporting. Without a DSN Sentry is not initialised at all.
    sentry_dsn: SecretStr | None = None
    sentry_release: str = ""
    # Exception messages can contain personal data; by default only the type is sent.
    sentry_include_exception_messages: bool = False
    sentry_traces_sample_rate: float = Field(default=0, ge=0, le=1)

    rate_limit_backend: Literal["postgres", "memory"] = "postgres"

    cors_origins: list[str] = ["http://localhost:3000"]
    trusted_hosts: list[str] = ["localhost", "127.0.0.1", "[::1]"]
    max_request_body_bytes: int = Field(default=1_048_576, gt=0)

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, origins: list[str]) -> list[str]:
        for origin in origins:
            if not ORIGIN_PATTERN.fullmatch(origin):
                raise ValueError(
                    "CORS origins must be explicit HTTP(S) origins (scheme://host[:port])"
                )
            HttpUrl(origin)
        return [without_default_port(origin.lower()) for origin in origins]

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, hosts: list[str]) -> list[str]:
        for host in hosts:
            if "*" in host and host != "*" and ("*" in host[1:] or not host.startswith("*.")):
                raise ValueError("Trusted host wildcards must use *.example.com")
        return hosts

    @field_validator("storage_endpoint_url", mode="before")
    @classmethod
    def blank_endpoint_is_unset(cls, value: object) -> object:
        # .env files list every variable; a blank one means "not configured".
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("min_supported_app_version", "latest_app_version")
    @classmethod
    def validate_app_version(cls, version: str) -> str:
        if not VERSION_PATTERN.fullmatch(version):
            raise ValueError("App versions look like 1.2.3 (an optional -suffix is ignored)")
        return version

    @field_validator("storage_allowed_content_types")
    @classmethod
    def validate_content_types(cls, types: list[str]) -> list[str]:
        for item in types:
            if not CONTENT_TYPE_PATTERN.fullmatch(item):
                raise ValueError("Storage content types must be exact (type/subtype), no wildcards")
        return [item.lower() for item in types]

    @field_validator("google_web_client_id", "google_android_client_id", "google_ios_client_id")
    @classmethod
    def validate_google_client_id(cls, client_id: str) -> str:
        if client_id and not GOOGLE_CLIENT_ID_PATTERN.fullmatch(client_id):
            raise ValueError("Google client IDs end with .apps.googleusercontent.com")
        return client_id

    @property
    def local(self) -> bool:
        return self.env in {"development", "test"}

    @property
    def signing_key(self) -> str:
        configured = secret_value(self.secret_key)
        if configured:
            return configured
        if self.env == "development":
            return LOCAL_SECRET
        raise ValueError("SECRET_KEY is required outside development")

    @property
    def jwt_key(self) -> str:
        configured = secret_value(self.jwt_secret_key)
        if configured:
            return configured
        # Development and test only (validated below): derive a distinct key.
        return hmac.new(self.signing_key.encode(), b"jwt-access-token", hashlib.sha256).hexdigest()

    @property
    def google_client_ids(self) -> list[str]:
        return [
            client_id
            for client_id in (
                self.google_web_client_id,
                self.google_android_client_id,
                self.google_ios_client_id,
            )
            if client_id
        ]

    @property
    def secure_cookies(self) -> bool:
        # Browsers drop Secure cookies on plain-HTTP origins other than localhost.
        return self.env != "development"

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        if self.env != "development":
            key = self.signing_key.strip()
            if len(key) < MIN_SECRET_LENGTH or key in PUBLISHED_SECRETS:
                raise ValueError("SECRET_KEY must be a unique secret of at least 32 characters")
            # Test may derive the access-token key; anything configured is checked too.
            if not self.local or secret_value(self.jwt_secret_key):
                self.validate_jwt_secret()
        if not self.local:
            if "*" in self.trusted_hosts:
                raise ValueError("TRUSTED_HOSTS cannot contain '*' in staging or production")
            if self.email_backend not in {"smtp", "resend"}:
                raise ValueError("EMAIL_BACKEND must be smtp or resend in staging and production")
            if self.rate_limit_backend != "postgres":
                raise ValueError("RATE_LIMIT_BACKEND must be postgres in staging and production")
            if self.web_url.scheme != "https":
                raise ValueError("WEB_URL must use https in staging and production")
        self.database()
        if self.migration_database_url:
            self.database(migration=True)
        if self.google_auth_enabled and not self.google_client_ids:
            raise ValueError(
                "GOOGLE_AUTH_ENABLED requires at least one of GOOGLE_WEB_CLIENT_ID, "
                "GOOGLE_ANDROID_CLIENT_ID or GOOGLE_IOS_CLIENT_ID"
            )
        if self.email_backend == "resend" and not secret_value(self.resend_api_key):
            raise ValueError("EMAIL_BACKEND=resend requires RESEND_API_KEY")
        if self.storage_backend == "s3":
            required = (
                self.storage_endpoint_url,
                self.storage_bucket,
                self.storage_access_key_id,
                secret_value(self.storage_secret_access_key),
            )
            if not all(required):
                raise ValueError(
                    "STORAGE_BACKEND=s3 requires STORAGE_ENDPOINT_URL, STORAGE_BUCKET, "
                    "STORAGE_ACCESS_KEY_ID and STORAGE_SECRET_ACCESS_KEY"
                )
            if self.storage_endpoint_url and (
                self.storage_endpoint_url.scheme != "https" and not self.local
            ):
                raise ValueError("STORAGE_ENDPOINT_URL must use https in staging and production")
        if self.job_timeout_seconds >= self.job_lock_timeout_seconds:
            raise ValueError("JOB_TIMEOUT_SECONDS must be shorter than JOB_LOCK_TIMEOUT_SECONDS")
        if bool(self.smtp_username) != bool(self.smtp_password.get_secret_value()):
            raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be set together")
        if self.smtp_security == "none":
            if self.smtp_username:
                raise ValueError("SMTP credentials require SMTP_SECURITY=starttls or tls")
            if not self.local and self.email_backend == "smtp" and not self.smtp_allow_insecure:
                raise ValueError(
                    "SMTP_SECURITY must be starttls or tls in staging and production "
                    "(SMTP_ALLOW_INSECURE=true allows a local relay)"
                )
        return self

    def validate_jwt_secret(self) -> None:
        jwt_secret = secret_value(self.jwt_secret_key).strip()
        # An HMAC key should be at least as long as the digest (RFC 7518 section 3.2).
        minimum = {"HS256": 32, "HS384": 48, "HS512": 64}[self.jwt_algorithm]
        if len(jwt_secret.encode()) < minimum or jwt_secret in PUBLISHED_SECRETS:
            raise ValueError(
                f"JWT_SECRET_KEY must be a unique secret of at least {minimum} bytes "
                f"for {self.jwt_algorithm}"
            )
        if hmac.compare_digest(jwt_secret.encode(), self.signing_key.strip().encode()):
            raise ValueError("JWT_SECRET_KEY must differ from SECRET_KEY")


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
