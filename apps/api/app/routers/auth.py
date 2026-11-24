"""
Authentication API routes.
Follows strict layering: uses AuthService, not repositories directly.
"""

from fastapi import APIRouter, Depends, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_active_user
from app.core.config import settings
from app.core.db import get_db
from app.models import User
from app.repositories.user import OAuthAccountRepository, UserRepository
from app.schemas.user import TokenResponse, UserLogin, UserRegister, UserResponse, UserUpdate
from app.services.auth import AuthService
from app.services.oauth import OAuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    """Dependency to get AuthService instance."""
    user_repository = UserRepository(db)
    return AuthService(user_repository)


def get_oauth_service(db: Session = Depends(get_db)) -> OAuthService:
    """Dependency to get OAuthService instance."""
    user_repository = UserRepository(db)
    oauth_account_repository = OAuthAccountRepository(db)
    return OAuthService(user_repository, oauth_account_repository)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(
    data: UserRegister,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """
    Register a new user with email and password.

    Returns access token and user information.
    """
    user = service.register_with_email(data)
    access_token = service.create_access_token_for_user(user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=TokenResponse)
def login(
    data: UserLogin,
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    """
    Authenticate user with email and password.

    Returns access token and user information.
    """
    user = service.authenticate_with_email(data)
    access_token = service.create_access_token_for_user(user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """
    Get current authenticated user information.

    Requires valid JWT token in Authorization header.
    """
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    data: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """
    Update current authenticated user profile.

    Requires valid JWT token in Authorization header.
    """
    updated_user = service.update_user_profile(current_user, data)
    return UserResponse.model_validate(updated_user)


@router.get("/google/login")
def google_login(
    oauth_service: OAuthService = Depends(get_oauth_service),
) -> dict[str, str]:
    """
    Initiate Google OAuth login flow.

    Returns authorization URL to redirect user to Google login page.
    """
    return oauth_service.get_google_authorization_url()


@router.get("/google/callback")
async def google_callback(
    code: str,
    oauth_service: OAuthService = Depends(get_oauth_service),
    auth_service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    """
    Handle Google OAuth callback.

    Exchanges code for token, creates/links user account,
    generates JWT token, and redirects to frontend with token.
    """
    # Complete OAuth flow and get user
    user = await oauth_service.authenticate_with_google(code)

    # Generate JWT access token
    access_token = auth_service.create_access_token_for_user(user)

    # Redirect to frontend with token
    redirect_url = f"{settings.frontend_url}/auth/callback?token={access_token}"
    return RedirectResponse(url=redirect_url)
