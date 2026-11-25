"""Device sessions: issuing tokens, refresh-token rotation and reuse detection."""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEventType, record_event
from app.core.client import ClientInfo
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.core.security import create_access_token, new_token, token_digest
from app.modules.auth.cookies import csrf_token_for
from app.modules.auth.models import AuthSession, SessionRevocation, SignInMethod, User
from app.modules.auth.repository import SessionRepository


@dataclass(frozen=True)
class IssuedTokens:
    session: AuthSession
    access_token: str
    expires_in: int
    refresh_token: str
    csrf_token: str
    # Seconds until the session expires; the refresh cookie's Max-Age.
    refresh_max_age: int


def require_recent_authentication(session: AuthSession, config: Settings) -> None:
    """Sensitive changes need a sign-in or re-authentication on this device within N minutes."""
    window = timedelta(minutes=config.reauthentication_max_age_minutes)
    if session.authenticated_at < datetime.now(UTC) - window:
        raise DomainError(ErrorCode.REAUTHENTICATION_REQUIRED)


class SessionService:
    def __init__(self, db: AsyncSession, config: Settings) -> None:
        self.db = db
        self.config = config
        self.sessions = SessionRepository(db)

    def expiry(self, now: datetime, created_at: datetime) -> datetime:
        idle = now + timedelta(days=self.config.refresh_token_expire_days)
        return min(idle, created_at + timedelta(days=self.config.session_max_age_days))

    async def start(
        self,
        user: User,
        method: SignInMethod,
        client: ClientInfo,
        device_name: str | None,
        *,
        authenticated_at: datetime | None = None,
    ) -> IssuedTokens:
        """Start a session. ``authenticated_at`` is when the user actually proved who they
        are, e.g. when Google issued the ID token; it defaults to now."""
        now = datetime.now(UTC)
        session = AuthSession(
            id=uuid.uuid4(),
            user_id=user.id,
            sign_in_method=method,
            platform=client.platform,
            device_name=device_name,
            user_agent=client.user_agent,
            ip_hash=client.ip_hash,
            authenticated_at=min(authenticated_at or now, now),
            last_used_at=now,
            expires_at=self.expiry(now, now),
            created_at=now,
        )
        refresh_token = new_token()
        await self.sessions.add(session, token_digest(refresh_token))
        return self.issue(user, session, refresh_token, now)

    def issue(
        self, user: User, session: AuthSession, refresh_token: str, now: datetime
    ) -> IssuedTokens:
        access_token, lifetime = create_access_token(user.id, session.id, self.config, now=now)
        return IssuedTokens(
            session=session,
            access_token=access_token,
            expires_in=lifetime,
            refresh_token=refresh_token,
            csrf_token=csrf_token_for(self.config, session.id),
            refresh_max_age=max(1, int((session.expires_at - now).total_seconds())),
        )

    async def rotate(
        self,
        refresh_token: str,
        client: ClientInfo,
        *,
        verify: Callable[[AuthSession], None] | None = None,
    ) -> tuple[IssuedTokens, User]:
        """Exchange a refresh token for new tokens. Each token works once.

        Presenting a token that was already exchanged means two parties hold the
        session's tokens; the whole session (the token family) is revoked.
        """
        now = datetime.now(UTC)
        found = await self.sessions.lock_by_refresh_token(token_digest(refresh_token))
        if found is None:
            raise DomainError(ErrorCode.INVALID_REFRESH_TOKEN)
        token, session, user = found
        if verify is not None:
            verify(session)  # CSRF for cookie requests, before any state changes.

        if token.used_at is not None:
            if session.revoked_at is None:
                session.revoked_at = now
                session.revoked_reason = SessionRevocation.REFRESH_TOKEN_REUSED
            record_event(
                self.db,
                AuditEventType.REFRESH_TOKEN_REUSED,
                client=client,
                user_id=user.id,
                session_id=session.id,
            )
            raise DomainError(ErrorCode.INVALID_REFRESH_TOKEN, commit=True)
        if session.revoked_at is not None or session.expires_at <= now:
            raise DomainError(ErrorCode.INVALID_REFRESH_TOKEN)
        if not user.is_active:
            raise DomainError(ErrorCode.INACTIVE_USER)

        token.used_at = now
        replacement = new_token()
        await self.sessions.add_refresh_token(session.id, token_digest(replacement))
        session.last_used_at = now
        session.expires_at = self.expiry(now, session.created_at)
        session.ip_hash = client.ip_hash or session.ip_hash
        session.user_agent = client.user_agent or session.user_agent
        await self.db.flush()
        return self.issue(user, session, replacement, now), user

    def revoke(self, session: AuthSession, reason: SessionRevocation) -> None:
        session.revoked_at = datetime.now(UTC)
        session.revoked_reason = reason
