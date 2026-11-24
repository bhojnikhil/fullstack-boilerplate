"""Authentication API routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse

from app.core import API_PREFIX
from app.core.config import Settings, get_settings
from app.core.db import RequestSession
from app.core.errors import ErrorEnvelope
from app.modules.auth.dependencies import CurrentUser, Mutation
from app.modules.auth.oauth import OAuthService
from app.modules.auth.repository import OAuthAccountRepository, UserRepository
from app.modules.auth.schemas import (
    TokenResponse,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdate,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix=f"{API_PREFIX}/auth", tags=["auth"])
Config = Annotated[Settings, Depends(get_settings)]


async def get_auth_service(db: RequestSession, config: Config) -> AuthService:
    return AuthService(UserRepository(db), config)


async def get_oauth_service(db: RequestSession, config: Config) -> OAuthService:
    return OAuthService(UserRepository(db), OAuthAccountRepository(db), config)


Auth = Annotated[AuthService, Depends(get_auth_service)]
OAuth = Annotated[OAuthService, Depends(get_oauth_service)]


@router.post(
    "/register", status_code=status.HTTP_201_CREATED, responses={409: {"model": ErrorEnvelope}}
)
async def register(request: Request, data: UserRegister, service: Auth) -> TokenResponse:
    user = await service.register_with_email(data)
    request.state.user_id = str(user.id)
    return TokenResponse(
        access_token=service.create_access_token_for_user(user),
        user=UserResponse.model_validate(user),
    )


@router.post("/login", responses={code: {"model": ErrorEnvelope} for code in (401, 403)})
async def login(request: Request, data: UserLogin, service: Auth) -> TokenResponse:
    user = await service.authenticate_with_email(data)
    request.state.user_id = str(user.id)
    return TokenResponse(
        access_token=service.create_access_token_for_user(user),
        user=UserResponse.model_validate(user),
    )


@router.get("/me", responses={code: {"model": ErrorEnvelope} for code in (401, 403)})
async def get_current_user_info(current_user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", responses={code: {"model": ErrorEnvelope} for code in (401, 403, 409)})
async def update_current_user(
    data: UserUpdate, current_user: CurrentUser, service: Auth, mutation: Mutation
) -> UserResponse:
    user = await service.update_user_profile(current_user, data)
    return mutation.save(UserResponse.model_validate(user))


@router.get("/google/login", responses={503: {"model": ErrorEnvelope}})
async def google_login(oauth_service: OAuth) -> dict[str, str]:
    return oauth_service.get_google_authorization_url()


@router.get("/google/callback", responses={503: {"model": ErrorEnvelope}})
async def google_callback(
    request: Request, code: str, oauth_service: OAuth, auth_service: Auth, config: Config
) -> RedirectResponse:
    user = await oauth_service.authenticate_with_google(code)
    request.state.user_id = str(user.id)
    access_token = auth_service.create_access_token_for_user(user)
    frontend_url = str(config.frontend_url).rstrip("/")
    return RedirectResponse(url=f"{frontend_url}/auth/callback?token={access_token}")
