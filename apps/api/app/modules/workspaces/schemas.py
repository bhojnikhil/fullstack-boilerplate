import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.core.pagination import Page
from app.modules.auth.models import User
from app.modules.workspaces.models import (
    InvitableRole,
    Invitation,
    Membership,
    Workspace,
    WorkspaceRole,
)
from app.modules.workspaces.validation import (
    MAX_SLUG_LENGTH,
    printable,
    validate_currency,
    validate_slug,
    validate_timezone,
)

WorkspaceName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(printable),
]
Slug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, to_lower=True, max_length=MAX_SLUG_LENGTH),
    AfterValidator(validate_slug),
]
Currency = Annotated[str, Field(min_length=3, max_length=3), AfterValidator(validate_currency)]
Timezone = Annotated[str, Field(max_length=64), AfterValidator(validate_timezone)]
InviteEmail = Annotated[
    EmailStr, Field(max_length=255), AfterValidator(lambda email: email.strip().lower())
]


class WorkspaceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WorkspaceName
    # Generated from the name when omitted.
    slug: Slug | None = None
    currency: Currency = "USD"
    timezone: Timezone = "UTC"


class WorkspaceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WorkspaceName | None = None
    slug: Slug | None = None
    currency: Currency | None = None
    timezone: Timezone | None = None


class WorkspaceResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    currency: str
    timezone: str
    # The caller's role in this workspace.
    role: WorkspaceRole
    created_at: datetime
    updated_at: datetime

    @classmethod
    def build(cls, workspace: Workspace, role: WorkspaceRole) -> "WorkspaceResponse":
        return cls(
            id=workspace.id,
            name=workspace.name,
            slug=workspace.slug,
            currency=workspace.currency,
            timezone=workspace.timezone,
            role=role,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
        )


class WorkspacePage(Page[WorkspaceResponse]):
    pass


class MemberResponse(BaseModel):
    user_id: uuid.UUID
    name: str
    avatar_url: str | None
    # Only admins and the owner see other members' email addresses.
    email: str | None
    role: WorkspaceRole
    joined_at: datetime


class MemberPage(Page[MemberResponse]):
    pass


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: InvitableRole


class OwnershipTransfer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: uuid.UUID


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # With an email, only that (verified) address can accept and the link is emailed.
    # Without one, the response carries a shareable link and token (for a QR code).
    email: InviteEmail | None = None
    role: InvitableRole = InvitableRole.MEMBER


class InvitationStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"
    EXPIRED = "expired"


class InvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str | None
    role: InvitableRole
    status: InvitationStatus
    expires_at: datetime
    created_at: datetime
    invited_by_id: uuid.UUID | None

    @classmethod
    def build(cls, invitation: Invitation, now: datetime) -> "InvitationResponse":
        status = InvitationStatus.PENDING
        if invitation.accepted_at is not None:
            status = InvitationStatus.ACCEPTED
        elif invitation.revoked_at is not None:
            status = InvitationStatus.REVOKED
        elif invitation.expires_at <= now:
            status = InvitationStatus.EXPIRED
        return cls(
            id=invitation.id,
            email=invitation.email,
            role=InvitableRole(invitation.role),
            status=status,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            invited_by_id=invitation.invited_by_id,
        )


class InvitationPage(Page[InvitationResponse]):
    pass


class CreatedInvitation(InvitationResponse):
    # Shown once, for link invitations only. Email invitations are delivered by email
    # and the API never returns their token.
    token: str | None
    link: str | None


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=20, max_length=200)


def member_response(membership: Membership, user: User, *, show_email: bool) -> MemberResponse:
    return MemberResponse(
        user_id=user.id,
        name=user.name,
        avatar_url=user.avatar_url,
        email=user.email if show_email else None,
        role=WorkspaceRole(membership.role),
        joined_at=membership.created_at,
    )
