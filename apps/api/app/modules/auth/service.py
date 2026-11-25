"""Account and password operations."""

from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository
from app.modules.auth.schemas import UserLogin, UserRegister, UserUpdate


class AuthService:
    def __init__(self, user_repository: UserRepository, config: Settings) -> None:
        self._user_repository = user_repository
        self._config = config

    async def register_with_email(self, data: UserRegister) -> User:
        if await self._user_repository.get_by_email(data.email) is not None:
            raise DomainError(ErrorCode.EMAIL_CONFLICT)

        hashed_password = await run_in_threadpool(hash_password, data.password)
        user = await self._user_repository.create_for_registration(
            email=data.email, name=data.name, hashed_password=hashed_password
        )
        if user is None:
            raise DomainError(ErrorCode.EMAIL_CONFLICT)
        return user

    async def authenticate_with_email(self, data: UserLogin) -> User:
        user = await self._user_repository.get_by_email(data.email)
        if user is None:
            raise DomainError(ErrorCode.INVALID_CREDENTIALS)
        if user.hashed_password is None:
            raise DomainError(
                ErrorCode.INVALID_CREDENTIALS,
                "This account uses social login. Please sign in with Google.",
            )
        if not await run_in_threadpool(verify_password, data.password, user.hashed_password):
            raise DomainError(ErrorCode.INVALID_CREDENTIALS)
        if not user.is_active:
            raise DomainError(ErrorCode.INACTIVE_USER)
        return user

    def create_access_token_for_user(self, user: User) -> str:
        return create_access_token({"sub": str(user.id), "email": user.email}, self._config)

    async def update_user_profile(self, user: User, data: UserUpdate) -> User:
        return await self._user_repository.update(user=user, name=data.name)
