import unicodedata
import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    model_validator,
)

from app.core.pagination import Page
from app.modules.auth.models import AuthSession, SignInMethod, User

# New passwords. Length is the only composition rule (NIST SP 800-63B). Existing
# shorter passwords keep working; the limit applies when a password is set.
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
# Bounds hashing work for submitted passwords without rejecting older long ones.
MAX_SUBMITTED_PASSWORD_LENGTH = 1024


def lowercase(email: str) -> str:
    return email.strip().lower()


def printable(value: str) -> str:
    if any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("Control characters are not allowed")
    return value


Email = Annotated[EmailStr, Field(max_length=255), AfterValidator(lowercase)]
DisplayName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    AfterValidator(printable),
]
NewPassword = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)]
SubmittedPassword = Annotated[str, Field(min_length=1, max_length=MAX_SUBMITTED_PASSWORD_LENGTH)]
OpaqueToken = Annotated[str, Field(min_length=16, max_length=128)]
GoogleIdToken = Annotated[str, Field(min_length=16, max_length=4096)]
DeviceName = Annotated[
    str | None,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(lambda value: printable(value) if value is not None else None),
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegisterRequest(Strict):
    email: Email
    password: NewPassword
    name: DisplayName


class LoginRequest(Strict):
    email: Email
    password: SubmittedPassword
    device_name: DeviceName = None


class GoogleSignInRequest(Strict):
    id_token: GoogleIdToken
    device_name: DeviceName = None


class GoogleLinkRequest(Strict):
    id_token: GoogleIdToken


class RefreshRequest(Strict):
    """Mobile and other non-browser clients send the refresh token in the body."""

    refresh_token: OpaqueToken


class TokenRequest(Strict):
    token: OpaqueToken


class EmailRequest(Strict):
    email: Email


class ResetPasswordRequest(Strict):
    token: OpaqueToken
    new_password: NewPassword


class ReauthenticateRequest(Strict):
    """Exactly one of ``password`` or a freshly issued Google ``id_token``."""

    password: SubmittedPassword | None = None
    id_token: GoogleIdToken | None = None

    @model_validator(mode="after")
    def one_credential(self) -> Self:
        if (self.password is None) == (self.id_token is None):
            raise ValueError("Provide exactly one of password or id_token")
        return self


class ChangePasswordRequest(Strict):
    current_password: SubmittedPassword
    new_password: NewPassword


class ChangeEmailRequest(Strict):
    new_email: Email


class UpdateProfileRequest(Strict):
    name: DisplayName | None = None


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    email_verified: bool
    name: str
    avatar_url: str | None
    sign_in_methods: list[SignInMethod]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, user: User, providers: list[SignInMethod]) -> "UserResponse":
        methods = [SignInMethod.PASSWORD] if user.hashed_password else []
        return cls(
            id=user.id,
            email=user.email,
            email_verified=user.email_verified,
            name=user.name,
            avatar_url=user.avatar_url,
            sign_in_methods=[*methods, *providers],
            created_at=user.created_at,
            updated_at=user.updated_at,
        )


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    refresh_token: str | None = Field(
        description="Returned to non-web clients only. Web clients get an httpOnly cookie."
    )
    csrf_token: str | None = Field(
        description="Web clients only: send it as X-CSRF-Token when refreshing with the cookie."
    )
    user: UserResponse


class AcceptedResponse(BaseModel):
    message: str


class SessionResponse(BaseModel):
    id: uuid.UUID
    current: bool
    sign_in_method: SignInMethod
    platform: str
    device_name: str | None
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime

    @classmethod
    def build(cls, session: AuthSession, current_id: uuid.UUID) -> "SessionResponse":
        return cls(
            id=session.id,
            current=session.id == current_id,
            sign_in_method=session.sign_in_method,
            platform=session.platform,
            device_name=session.device_name,
            user_agent=session.user_agent,
            created_at=session.created_at,
            last_used_at=session.last_used_at,
            expires_at=session.expires_at,
        )


class SessionPage(Page[SessionResponse]):
    pass


class RevokedSessionsResponse(BaseModel):
    revoked: int
