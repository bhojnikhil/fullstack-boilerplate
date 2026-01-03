"""
OAuth service for handling Google OAuth 2.0 authentication.
Supports account linking and OAuth-only user creation.
"""

import secrets
import uuid
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.models import User
from app.models.enums import OAuthProvider
from app.repositories.user import OAuthAccountRepository, UserRepository


class OAuthService:
    """
    Service for handling OAuth authentication flow.
    Follows strict layering: uses repositories for all database operations.
    """

    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(
        self,
        user_repository: UserRepository,
        oauth_account_repository: OAuthAccountRepository,
    ) -> None:
        self._user_repository = user_repository
        self._oauth_account_repository = oauth_account_repository

    def get_google_authorization_url(self) -> dict[str, str]:
        """
        Generate Google OAuth authorization URL.

        Returns:
            Dictionary with authorization_url and state token
        """
        if not settings.google_client_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth is not configured",
            )

        state = secrets.token_urlsafe(32)
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }

        auth_url = f"{self.GOOGLE_AUTH_URL}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        return {"authorization_url": auth_url, "state": state}

    async def authenticate_with_google(self, code: str) -> User:
        """
        Complete OAuth flow: exchange code for token, fetch user info,
        create or link account.

        Args:
            code: Authorization code from Google

        Returns:
            User object (existing or newly created)

        Raises:
            HTTPException: If OAuth flow fails
        """
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Google OAuth is not configured",
            )

        # Step 1: Exchange code for access token
        token_data = await self._exchange_code_for_token(code)
        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")

        # Step 2: Fetch user info from Google
        user_info = await self._fetch_google_user_info(access_token)
        provider_account_id = user_info["id"]
        email = user_info["email"]
        name = user_info.get("name", email.split("@")[0])
        avatar_url = user_info.get("picture")

        # Step 3: Find or create user (supports account linking)
        user = await self._find_or_create_user(
            provider_account_id=provider_account_id,
            email=email,
            name=name,
            avatar_url=avatar_url,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        return user

    async def _exchange_code_for_token(self, code: str) -> dict[str, Any]:
        """Exchange authorization code for access token."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to exchange code for token",
                )

            return response.json()

    async def _fetch_google_user_info(self, access_token: str) -> dict[str, Any]:
        """Fetch user information from Google."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to fetch Google user info",
                )

            return response.json()

    async def _find_or_create_user(
        self,
        provider_account_id: str,
        email: str,
        name: str,
        avatar_url: str | None,
        access_token: str,
        refresh_token: str | None,
    ) -> User:
        """Find or create user, with support for account linking."""
        # Check if OAuth account already exists
        oauth_account = self._oauth_account_repository.get_by_provider_and_account_id(
            provider=OAuthProvider.GOOGLE, provider_account_id=provider_account_id
        )

        if oauth_account is not None:
            # OAuth account exists, return linked user
            user = self._user_repository.get_by_id(uuid.UUID(str(oauth_account.user_id)))
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="User not found",
                )
            return user

        # Check if user exists with same email (account linking)
        existing_user = self._user_repository.get_by_email(email)
        if existing_user is not None:
            # Link OAuth to existing user
            self._oauth_account_repository.create(
                user_id=existing_user.id,
                provider=OAuthProvider.GOOGLE,
                provider_account_id=provider_account_id,
                access_token=access_token,
                refresh_token=refresh_token,
            )
            return existing_user

        # Create new user
        new_user = self._user_repository.create(
            email=email, name=name, avatar_url=avatar_url, hashed_password=None
        )

        # Link OAuth account
        self._oauth_account_repository.create(
            user_id=new_user.id,
            provider=OAuthProvider.GOOGLE,
            provider_account_id=provider_account_id,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        return new_user
