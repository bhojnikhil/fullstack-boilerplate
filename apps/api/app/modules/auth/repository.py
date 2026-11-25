"""Auth persistence. Repositories add, flush and query; they never commit.

Expiry checks use the application clock, the same clock that computed the
expiry times, so they do not depend on the database server's clock.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Cursor
from app.modules.auth.models import (
    AccountToken,
    AccountTokenPurpose,
    AuthSession,
    OAuthAccount,
    OAuthProvider,
    RefreshToken,
    SessionRevocation,
    User,
)


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        # lower() on both sides uses ux_users_email_lower and matches legacy mixed-case rows.
        stmt = select(User).where(func.lower(User.email) == email.lower())
        return await self._db.scalar(stmt)

    async def create(
        self,
        email: str,
        name: str,
        *,
        hashed_password: str | None = None,
        avatar_url: str | None = None,
        email_verified_at: datetime | None = None,
    ) -> User | None:
        """Insert a user, or return None if the email is already taken (even concurrently)."""
        stmt = (
            insert(User)
            .values(
                id=uuid.uuid4(),
                email=email,
                name=name,
                hashed_password=hashed_password,
                avatar_url=avatar_url,
                email_verified_at=email_verified_at,
                is_active=True,
            )
            .on_conflict_do_nothing()
            .returning(User)
        )
        return await self._db.scalar(stmt)

    async def delete(self, user: User) -> None:
        await self._db.delete(user)
        await self._db.flush()


class OAuthAccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, provider: OAuthProvider, subject: str) -> OAuthAccount | None:
        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == provider, OAuthAccount.provider_account_id == subject
        )
        return await self._db.scalar(stmt)

    async def get_for_user(
        self, user_id: uuid.UUID, provider: OAuthProvider
    ) -> OAuthAccount | None:
        stmt = select(OAuthAccount).where(
            OAuthAccount.user_id == user_id, OAuthAccount.provider == provider
        )
        return await self._db.scalar(stmt)

    async def providers_for_user(self, user_id: uuid.UUID) -> list[OAuthProvider]:
        stmt = select(OAuthAccount.provider).where(OAuthAccount.user_id == user_id)
        return sorted(OAuthProvider(provider) for provider in await self._db.scalars(stmt))

    async def delete(self, account: OAuthAccount) -> None:
        await self._db.delete(account)
        await self._db.flush()


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, session: AuthSession, refresh_token_hash: str) -> None:
        self._db.add(session)
        await self._db.flush()
        await self.add_refresh_token(session.id, refresh_token_hash)

    async def add_refresh_token(self, session_id: uuid.UUID, token_hash: str) -> None:
        self._db.add(RefreshToken(session_id=session_id, token_hash=token_hash))
        await self._db.flush()

    async def get_active_with_user(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[AuthSession, User] | None:
        stmt = (
            select(AuthSession, User)
            .join(User, User.id == AuthSession.user_id)
            .where(
                AuthSession.id == session_id,
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(UTC),
            )
        )
        row = (await self._db.execute(stmt)).one_or_none()
        return (row[0], row[1]) if row is not None else None

    async def lock_by_refresh_token(
        self, token_hash: str
    ) -> tuple[RefreshToken, AuthSession, User] | None:
        """Lock the token and its session so concurrent refreshes are serialized."""
        stmt = (
            select(RefreshToken, AuthSession, User)
            .join(AuthSession, AuthSession.id == RefreshToken.session_id)
            .join(User, User.id == AuthSession.user_id)
            .where(RefreshToken.token_hash == token_hash)
            .with_for_update(of=(RefreshToken, AuthSession))
        )
        row = (await self._db.execute(stmt)).one_or_none()
        return (row[0], row[1], row[2]) if row is not None else None

    async def get_active_for_user(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> AuthSession | None:
        stmt = select(AuthSession).where(
            AuthSession.id == session_id,
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
        return await self._db.scalar(stmt)

    async def list_active(
        self, user_id: uuid.UUID, limit: int, before: Cursor | None
    ) -> list[AuthSession]:
        stmt = select(AuthSession).where(
            AuthSession.user_id == user_id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
        if before is not None:
            stmt = stmt.where(tuple_(AuthSession.created_at, AuthSession.id) < before)
        stmt = stmt.order_by(AuthSession.created_at.desc(), AuthSession.id.desc()).limit(limit)
        return list(await self._db.scalars(stmt))

    async def revoke_all(
        self,
        user_id: uuid.UUID,
        reason: SessionRevocation,
        *,
        keep: uuid.UUID | None = None,
    ) -> int:
        stmt = (
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
            .returning(AuthSession.id)
            .execution_options(synchronize_session=False)
        )
        if keep is not None:
            stmt = stmt.where(AuthSession.id != keep)
        return len((await self._db.scalars(stmt)).all())


class AccountTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(
        self,
        user_id: uuid.UUID,
        purpose: AccountTokenPurpose,
        token_hash: str,
        email: str,
        expires_at: datetime,
    ) -> None:
        self._db.add(
            AccountToken(
                user_id=user_id,
                purpose=purpose,
                token_hash=token_hash,
                email=email,
                expires_at=expires_at,
                created_at=datetime.now(UTC),
            )
        )
        await self._db.flush()

    async def lock_valid(
        self, purpose: AccountTokenPurpose, token_hash: str
    ) -> AccountToken | None:
        stmt = (
            select(AccountToken)
            .where(
                AccountToken.purpose == purpose,
                AccountToken.token_hash == token_hash,
                AccountToken.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        return await self._db.scalar(stmt)

    async def delete_for_user(self, user_id: uuid.UUID, purpose: AccountTokenPurpose) -> None:
        await self._db.execute(
            delete(AccountToken)
            .where(AccountToken.user_id == user_id, AccountToken.purpose == purpose)
            .execution_options(synchronize_session=False)
        )
