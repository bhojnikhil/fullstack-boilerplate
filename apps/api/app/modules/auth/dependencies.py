from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core import rls
from app.core.config import Settings, get_settings
from app.core.db import RequestSession
from app.core.errors import DomainError, ErrorCode
from app.core.idempotency import Idempotency, begin_idempotency
from app.core.security import InvalidAccessTokenError, decode_access_token
from app.modules.auth.models import AuthSession, User
from app.modules.auth.repository import SessionRepository

security = HTTPBearer()


@dataclass(frozen=True)
class AuthContext:
    user: User
    session: AuthSession


async def get_auth_context(
    request: Request,
    db: RequestSession,
    config: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> AuthContext:
    try:
        claims = decode_access_token(credentials.credentials, config)
    except InvalidAccessTokenError as err:
        raise DomainError(ErrorCode.INVALID_TOKEN) from err

    # The session must still be active: sign-out and revocation take effect immediately.
    found = await SessionRepository(db).get_active_with_user(claims.session_id, claims.user_id)
    if found is None:
        raise DomainError(ErrorCode.INVALID_TOKEN)
    session, user = found
    request.state.user_id = str(user.id)
    if not user.is_active:
        raise DomainError(ErrorCode.INACTIVE_USER)
    # Row-level security compares tenant rows with this user for the rest of the request.
    await rls.bind(db, rls.USER_ID, str(user.id))
    return AuthContext(user, session)


Auth = Annotated[AuthContext, Depends(get_auth_context)]


async def get_current_active_user(context: Auth) -> User:
    return context.user


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
