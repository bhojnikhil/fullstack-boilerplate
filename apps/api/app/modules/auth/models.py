import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class OAuthProvider(StrEnum):
    GOOGLE = "google"
    # Sign in with Apple would be added here; see docs/adr/0006-google-id-token-sign-in.md.


class SignInMethod(StrEnum):
    PASSWORD = "password"
    GOOGLE = "google"


class SessionRevocation(StrEnum):
    LOGOUT = "logout"
    USER_REVOKED = "user_revoked"
    REVOKED_OTHERS = "revoked_others"
    REFRESH_TOKEN_REUSED = "refresh_token_reused"
    PASSWORD_CHANGED = "password_changed"
    PASSWORD_RESET = "password_reset"


class AccountTokenPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
    CHANGE_EMAIL = "change_email"


class User(Base, UUIDMixin, TimestampMixin):
    """User account model."""

    __tablename__ = "users"
    # Load server-side timestamps during flush (RETURNING) instead of lazily, which
    # async sessions cannot do implicitly.
    __mapper_args__ = {"eager_defaults": True}

    # ix_users_email (exact-case unique) is redundant with ux_users_email_lower below. It
    # stays for one release because the previous release inserts with ON CONFLICT (email).
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


# Emails are stored lowercased. Matching on lower(email) also covers rows written by
# earlier releases, which kept the case as typed.
Index("ux_users_email_lower", func.lower(User.email), unique=True)


class OAuthAccount(Base, UUIDMixin, TimestampMixin):
    """A linked external identity. Provider access/refresh tokens are never stored."""

    __tablename__ = "oauth_accounts"
    __table_args__ = (
        UniqueConstraint("provider", "provider_account_id"),
        UniqueConstraint("user_id", "provider", name="uq_oauth_accounts_user_id_provider"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[OAuthProvider] = mapped_column(String(50), nullable=False)
    provider_account_id: Mapped[str] = mapped_column(String(255), nullable=False)


class AuthSession(Base, UUIDMixin, TimestampMixin):
    """One signed-in device. Its refresh tokens form a single rotation family."""

    __tablename__ = "auth_sessions"
    __table_args__ = (Index("ix_auth_sessions_user_created_id", "user_id", "created_at", "id"),)
    __mapper_args__ = {"eager_defaults": True}

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    sign_in_method: Mapped[SignInMethod] = mapped_column(String(16))
    platform: Mapped[str] = mapped_column(String(16))
    device_name: Mapped[str | None] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(100))
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    # Last password/Google sign-in or re-authentication on this device.
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[SessionRevocation | None] = mapped_column(String(32))


class RefreshToken(Base, UUIDMixin):
    __tablename__ = "refresh_tokens"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("auth_sessions.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 of the opaque token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Set when rotated. Presenting a used token again revokes the session.
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccountToken(Base, UUIDMixin):
    """Single-use emailed tokens: email verification, password reset, email change."""

    __tablename__ = "account_tokens"
    __table_args__ = (Index("ix_account_tokens_user_id_purpose", "user_id", "purpose"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    purpose: Mapped[AccountTokenPurpose] = mapped_column(String(32))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    # The address the token was sent to; it must still match when the token is used.
    email: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
