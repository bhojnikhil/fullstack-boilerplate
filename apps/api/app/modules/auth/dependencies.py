import uuid
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError

from app.core.config import Settings, get_settings
from app.core.db import RequestSession
from app.core.errors import DomainError, ErrorCode
from app.core.idempotency import Idempotency, begin_idempotency
from app.core.security import decode_access_token
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository

security = HTTPBearer()


async def get_current_user(
    request: Request,
    db: RequestSession,
    config: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> User:
    error = DomainError(ErrorCode.INVALID_CREDENTIALS, "Could not validate credentials")
    try:
        subject = decode_access_token(credentials.credentials, config).get("sub")
        if not isinstance(subject, str):
            raise error
        user_id = uuid.UUID(subject)
    except (JWTError, ValueError) as err:
        raise error from err

    user = await UserRepository(db).get_by_id(user_id)
    if user is None:
        raise error
    request.state.user_id = str(user.id)
    return user


async def get_current_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not current_user.is_active:
        raise DomainError(ErrorCode.INACTIVE_USER)
    return current_user


CurrentUser = Annotated[User, Depends(get_current_active_user)]


async def get_idempotency(
    request: Request,
    db: RequestSession,
    current_user: CurrentUser,
    key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Idempotency:
    if key is None:
        return Idempotency(db)
    return await begin_idempotency(db, current_user.id, key, request)


Mutation = Annotated[Idempotency, Depends(get_idempotency)]
