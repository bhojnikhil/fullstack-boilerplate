"""Auth persistence. Repositories add, flush and query; they never commit.

Expiry checks use the application clock, the same clock that computed the
expiry times, so they do not depend on the database server's clock.

Locking order: anything that changes a user's credentials, sessions or emailed
tokens locks the user row first (``UserRepository.lock``), then other rows. Code
that creates a user or changes an email also takes the address's advisory lock
(``lock_email``) so two requests cannot race for one address.
"""

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, and_, delete, exists, func, select, tuple_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.pagination import Cursor
from app.modules.auth.models import (
    AccountToken,
    AccountTokenPurpose,
    AuthSession,
    OAuthAccount,
    OAuthLinkState,
    OAuthProvider,
    RefreshToken,
    SessionRevocation,
    SignInMethod,
    User,
)


async def lock_email(db: AsyncSession, email: str) -> None:
    """Serialize work on one email address until the transaction ends."""
    digest = hashlib.sha256(b"email:" + email.strip().lower().encode()).digest()
    await db.execute(select(func.pg_advisory_xact_lock(int.from_bytes(digest[:8], signed=True))))


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        # lower() on both sides uses ux_users_email_lower and matches legacy mixed-case rows.
        stmt = select(User).where(func.lower(User.email) == email.lower())
        return await self._db.scalar(stmt)

    async def lock(self, user_id: uuid.UUID) -> User | None:
        """Lock the user row and reload it, so checks see the latest committed state."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self._db.scalar(stmt)

    async def create(
        self,
        email: str,
        name: str,
        *,
        avatar_url: str | None = None,
        email_verified_at: datetime | None = None,
    ) -> User | None:
        """Insert a user without a password, or return None if the email is taken."""
        await lock_email(self._db, email)
        stmt = (
            insert(User)
            .values(
                id=uuid.uuid4(),
                email=email,
                name=name,
                avatar_url=avatar_url,
                email_verified_at=email_verified_at,
                is_active=True,
            )
            .on_conflict_do_nothing()
            .returning(User)
        )
        return await self._db.scalar(stmt)

    async def change_email(self, user: User, email: str) -> bool:
        """Switch to a verified address unless another account uses it (no error raised)."""
        await lock_email(self._db, email)
        other = aliased(User)
        stmt = (
            update(User)
            .where(
                User.id == user.id,
                ~exists().where(
                    and_(func.lower(other.email) == email.lower(), other.id != user.id)
                ),
            )
            .values(email=email, email_verified_at=datetime.now(UTC))
            .returning(User.id)
            .execution_options(synchronize_session=False)
        )
        changed = await self._db.scalar(stmt) is not None
        if changed:
            await self.lock(user.id)  # Reload the changed row into the session.
        return changed

    async def delete(self, user: User) -> None:
        await self._db.delete(user)
        await self._db.flush()


class OAuthAccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, provider: OAuthProvider, subject: str) -> OAuthAccount | None:
        stmt = (
            select(OAuthAccount)
            .where(OAuthAccount.provider == provider, OAuthAccount.provider_account_id == subject)
            .execution_options(populate_existing=True)
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
        """Providers the user can sign in with."""
        stmt = select(OAuthAccount.provider).where(
            OAuthAccount.user_id == user_id, OAuthAccount.state == OAuthLinkState.LINKED
        )
        return sorted(OAuthProvider(provider) for provider in await self._db.scalars(stmt))

    async def add(self, user_id: uuid.UUID, provider: OAuthProvider, subject: str) -> bool:
        """Insert a usable link. False if the subject or the user's provider slot is taken."""
        stmt = (
            insert(OAuthAccount)
            .values(
                id=uuid.uuid4(),
                user_id=user_id,
                provider=provider,
                provider_account_id=subject,
                state=OAuthLinkState.LINKED,
            )
            .on_conflict_do_nothing()
            .returning(OAuthAccount.id)
        )
        return await self._db.scalar(stmt) is not None

    async def delete(self, account: OAuthAccount) -> None:
        await self._db.delete(account)
        await self._db.flush()

    async def delete_for_user(
        self, user_id: uuid.UUID, *, state: OAuthLinkState | None = None
    ) -> int:
        conditions = [OAuthAccount.user_id == user_id]
        if state is not None:
            conditions.append(OAuthAccount.state == state)
        stmt = (
            delete(OAuthAccount)
            .where(*conditions)
            .returning(OAuthAccount.id)
            .execution_options(synchronize_session="fetch")
        )
        return len((await self._db.scalars(stmt)).all())


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
        method: SignInMethod | None = None,
    ) -> list[uuid.UUID]:
        """Revoke the user's active sessions (optionally only one sign-in method's)."""
        stmt = (
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC), revoked_reason=reason)
            .returning(AuthSession.id)
            .execution_options(synchronize_session="fetch")
        )
        if keep is not None:
            stmt = stmt.where(AuthSession.id != keep)
        if method is not None:
            stmt = stmt.where(AuthSession.sign_in_method == method)
        return list((await self._db.scalars(stmt)).all())


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
        *,
        password_hash: str | None = None,
        pending_name: str | None = None,
    ) -> None:
        self._db.add(
            AccountToken(
                user_id=user_id,
                purpose=purpose,
                token_hash=token_hash,
                email=email,
                password_hash=password_hash,
                pending_name=pending_name,
                expires_at=expires_at,
                created_at=datetime.now(UTC),
            )
        )
        await self._db.flush()

    def _valid(self, purpose: AccountTokenPurpose, token_hash: str) -> Select[AccountToken]:
        return select(AccountToken).where(
            AccountToken.purpose == purpose,
            AccountToken.token_hash == token_hash,
            AccountToken.expires_at > datetime.now(UTC),
        )

    async def find_valid(
        self, purpose: AccountTokenPurpose, token_hash: str
    ) -> AccountToken | None:
        return await self._db.scalar(self._valid(purpose, token_hash))

    async def lock_valid(
        self, purpose: AccountTokenPurpose, token_hash: str
    ) -> AccountToken | None:
        """Re-read and lock the token. Call after locking its user (see the module docstring)."""
        stmt = (
            self._valid(purpose, token_hash)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self._db.scalar(stmt)

    async def trim_verifications(self, user_id: uuid.UUID, keep: int) -> None:
        # Called with the user locked. Preserve the newest bounded set.
        old = (
            select(AccountToken.id)
            .where(
                AccountToken.user_id == user_id,
                AccountToken.purpose == AccountTokenPurpose.VERIFY_EMAIL,
            )
            .order_by(AccountToken.created_at.desc(), AccountToken.id.desc())
            .offset(keep)
        )
        await self._db.execute(delete(AccountToken).where(AccountToken.id.in_(old)))

    async def latest(self, user_id: uuid.UUID, purpose: AccountTokenPurpose) -> AccountToken | None:
        stmt = (
            select(AccountToken)
            .where(AccountToken.user_id == user_id, AccountToken.purpose == purpose)
            .order_by(AccountToken.created_at.desc())
            .limit(1)
        )
        return await self._db.scalar(stmt)

    async def delete_for_user(self, user_id: uuid.UUID, *purposes: AccountTokenPurpose) -> None:
        """Delete the user's tokens of the given purposes (all purposes if none given)."""
        stmt = delete(AccountToken).where(AccountToken.user_id == user_id)
        if purposes:
            stmt = stmt.where(AccountToken.purpose.in_(purposes))
        await self._db.execute(stmt.execution_options(synchronize_session=False))
