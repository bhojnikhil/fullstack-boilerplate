"""
Authentication service - business logic only.
Follows strict layering: uses repositories for database access.
"""

from fastapi import HTTPException, status

from app.auth.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.models import User
from app.repositories import UserRepository
from app.schemas.user import UserLogin, UserRegister, UserUpdate


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self._user_repository = user_repository

    def register_with_email(self, data: UserRegister) -> User:
        """
        Register a new user with email and password.

        Args:
            data: User registration data

        Returns:
            Created user

        Raises:
            HTTPException: If email already exists
        """
        # Check if user already exists
        existing_user = self._user_repository.get_by_email(data.email)
        if existing_user is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        # Hash password
        hashed_password = hash_password(data.password)

        # Create user via repository
        user = self._user_repository.create(
            email=data.email,
            name=data.name,
            hashed_password=hashed_password,
        )

        return user

    def authenticate_with_email(self, data: UserLogin) -> User:
        """
        Authenticate user with email and password.

        Args:
            data: User login credentials

        Returns:
            Authenticated user

        Raises:
            HTTPException: If credentials are invalid
        """
        # Get user from database
        user = self._user_repository.get_by_email(data.email)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        # Verify password
        if user.hashed_password is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="This account uses social login. Please sign in with Google.",
            )

        if not verify_password(data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
            )

        # Check if user is active
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        return user

    def create_access_token_for_user(self, user: User) -> str:
        """
        Create JWT access token for a user.

        Args:
            user: User to create token for

        Returns:
            JWT access token string
        """
        token_data = {"sub": str(user.id), "email": user.email}
        return create_access_token(token_data)

    def update_user_profile(self, user: User, data: UserUpdate) -> User:
        """
        Update user profile information.

        Args:
            user: User to update
            data: Update data

        Returns:
            Updated user
        """
        return self._user_repository.update(
            user=user,
            name=data.name,
        )
