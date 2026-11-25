"""Google OAuth exchange and account linking."""

import secrets
from urllib.parse import urlencode

import httpx
from httpx import AsyncClient
from pydantic import BaseModel, ValidationError
from structlog.contextvars import get_contextvars

from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.core.middleware import REQUEST_ID
from app.modules.auth.models import OAuthProvider, User
from app.modules.auth.repository import OAuthAccountRepository, UserRepository


class GoogleTokens(BaseModel):
    access_token: str
    refresh_token: str | None = None


class GoogleProfile(BaseModel):
    id: str
    email: str
    name: str | None = None
    picture: str | None = None


class OAuthService:
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(
        self,
        user_repository: UserRepository,
        oauth_account_repository: OAuthAccountRepository,
        config: Settings,
    ) -> None:
        self._user_repository = user_repository
        self._oauth_account_repository = oauth_account_repository
        self._config = config

    def get_google_authorization_url(self) -> dict[str, str]:
        if not self._config.google_client_id:
            raise DomainError(ErrorCode.OAUTH_UNAVAILABLE)

        state = secrets.token_urlsafe(32)
        params = {
            "client_id": self._config.google_client_id,
            "redirect_uri": str(self._config.google_redirect_uri),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        return {"authorization_url": f"{self.GOOGLE_AUTH_URL}?{urlencode(params)}", "state": state}

    async def authenticate_with_google(self, code: str) -> User:
        if not self._config.google_client_id:
            raise DomainError(ErrorCode.OAUTH_UNAVAILABLE)

        request_id = get_contextvars().get("request_id")
        headers = {REQUEST_ID: request_id} if isinstance(request_id, str) else {}
        try:
            async with AsyncClient(timeout=httpx.Timeout(5, connect=2), headers=headers) as client:
                response = await client.post(
                    self.GOOGLE_TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": self._config.google_client_id,
                        "client_secret": self._config.google_client_secret.get_secret_value(),
                        "redirect_uri": str(self._config.google_redirect_uri),
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                tokens = GoogleTokens.model_validate_json(response.content)

                response = await client.get(
                    self.GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {tokens.access_token}"},
                )
                response.raise_for_status()
                profile = GoogleProfile.model_validate_json(response.content)
        except (httpx.HTTPError, ValidationError) as err:
            raise DomainError(ErrorCode.OAUTH_FAILED) from err

        return await self._find_or_create_user(profile, tokens)

    async def _find_or_create_user(self, profile: GoogleProfile, tokens: GoogleTokens) -> User:
        account = await self._oauth_account_repository.get_by_provider_and_account_id(
            provider=OAuthProvider.GOOGLE, provider_account_id=profile.id
        )
        if account is not None:
            user = await self._user_repository.get_by_id(account.user_id)
            if user is None:
                raise RuntimeError("OAuth account has no linked user")
            return user

        user = await self._user_repository.get_by_email(profile.email)
        if user is None:
            user = await self._user_repository.create(
                email=profile.email,
                name=profile.name or profile.email.split("@")[0],
                avatar_url=profile.picture,
            )

        await self._oauth_account_repository.create(
            user_id=user.id,
            provider=OAuthProvider.GOOGLE,
            provider_account_id=profile.id,
            access_token=tokens.access_token,
            refresh_token=tokens.refresh_token,
        )
        return user
