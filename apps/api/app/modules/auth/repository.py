import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auth.models import OAuthAccount, OAuthProvider, User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        return await self._db.scalar(stmt)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        return await self._db.scalar(stmt)

    async def create(
        self,
        email: str,
        name: str,
        hashed_password: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        user = User(
            email=email,
            name=name,
            hashed_password=hashed_password,
            avatar_url=avatar_url,
        )
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user

    async def create_for_registration(
        self, email: str, name: str, hashed_password: str
    ) -> User | None:
        stmt = (
            insert(User)
            .values(email=email, name=name, hashed_password=hashed_password)
            .on_conflict_do_nothing(index_elements=[User.email])
            .returning(User)
        )
        return await self._db.scalar(stmt)

    async def update(
        self,
        user: User,
        name: str | None = None,
        avatar_url: str | None = None,
    ) -> User:
        if name is not None:
            user.name = name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        await self._db.flush()
        await self._db.refresh(user)
        return user


class OAuthAccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_provider_and_account_id(
        self, provider: OAuthProvider, provider_account_id: str
    ) -> OAuthAccount | None:
        stmt = select(OAuthAccount).where(
            OAuthAccount.provider == provider,
            OAuthAccount.provider_account_id == provider_account_id,
        )
        return await self._db.scalar(stmt)

    async def create(
        self,
        user_id: uuid.UUID,
        provider: OAuthProvider,
        provider_account_id: str,
        access_token: str,
        refresh_token: str | None = None,
    ) -> OAuthAccount:
        oauth_account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        self._db.add(oauth_account)
        await self._db.flush()
        await self._db.refresh(oauth_account)
        return oauth_account
