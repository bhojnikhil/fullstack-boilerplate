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
ORIGIN_PATTERN = re.compile(r"https?://(?:[a-zA-Z0-9.-]+|\[[0-9a-fA-F:.]+\])(?::[0-9]+)?")


def postgres_url(value: str) -> URL:
    try:
        url = make_url(value)
    except (ArgumentError, ValueError):
        raise ValueError("Invalid PostgreSQL database URL") from None
    if url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise ValueError("Database URLs must use PostgreSQL with psycopg 3")
    return url.set(drivername="postgresql+psycopg")


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
        if self.env in {"development", "test"}:
            return postgres_url(DEFAULT_DATABASE_URL)
        raise ValueError("A database URL is required in staging and production")


class Settings(DatabaseSettings):
    secret_key: SecretStr | None = None
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=10080, gt=0)

    google_client_id: str = ""
    google_client_secret: SecretStr = SecretStr("")
    google_redirect_uri: HttpUrl = HttpUrl("http://localhost:8000/v1/auth/google/callback")
    frontend_url: HttpUrl = HttpUrl("http://localhost:3000")

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
        return origins

    @field_validator("trusted_hosts")
    @classmethod
    def validate_trusted_hosts(cls, hosts: list[str]) -> list[str]:
        for host in hosts:
            if "*" in host and host != "*" and ("*" in host[1:] or not host.startswith("*.")):
                raise ValueError("Trusted host wildcards must use *.example.com")
        return hosts

    @property
    def signing_key(self) -> str:
        if self.secret_key is None:
            return LOCAL_SECRET
        return self.secret_key.get_secret_value()

    @model_validator(mode="after")
    def validate_configuration(self) -> Self:
        if self.env in {"staging", "production"} and (
            len(self.signing_key.strip()) < 32
            or self.signing_key
            in {
                LOCAL_SECRET,
                "test-secret-key-do-not-use-in-production-12345678",
            }
        ):
            raise ValueError("SECRET_KEY must be a unique secret of at least 32 characters")
        if self.env in {"staging", "production"} and "*" in self.trusted_hosts:
            raise ValueError("TRUSTED_HOSTS cannot contain '*' in staging or production")
        self.database()
        if self.migration_database_url:
            self.database(migration=True)
        if bool(self.google_client_id) != bool(self.google_client_secret.get_secret_value()):
            raise ValueError("GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set together")
        return self


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings
