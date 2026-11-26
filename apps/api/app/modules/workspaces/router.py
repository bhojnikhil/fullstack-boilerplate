"""Workspace management routes.

Routes under ``/v1/workspaces/{workspace_id}`` authorize the workspace in the path;
the ``X-Workspace-Id`` header is for domain data (see ``dependencies``). A caller who
is not a member of the workspace gets 404 from every one of these routes.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.core import API_PREFIX
from app.core.client import Client
from app.core.config import Settings, get_settings
from app.core.db import RequestSession
from app.core.errors import ErrorEnvelope
from app.core.pagination import DEFAULT_PAGE_SIZE, PageCursor, PageSize
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.integrations.email import Mail
from app.modules.auth.dependencies import Auth, CurrentUser, Mutation
from app.modules.workspaces.dependencies import (
    PathWorkspace,
    WorkspaceContext,
    require_role,
)
from app.modules.workspaces.models import WorkspaceRole
from app.modules.workspaces.schemas import (
    CreatedInvitation,
    InvitationAccept,
    InvitationCreate,
    InvitationPage,
    InvitationResponse,
    MemberPage,
    OwnershipTransfer,
    RoleUpdate,
    WorkspaceCreate,
    WorkspacePage,
    WorkspaceResponse,
    WorkspaceUpdate,
    member_response,
)
from app.modules.workspaces.service import WorkspaceService

router = APIRouter(
    prefix=f"{API_PREFIX}/workspaces",
    tags=["workspaces"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403)},
)
invitations_router = APIRouter(
    prefix=f"{API_PREFIX}/invitations",
    tags=["invitations"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403)},
)
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorEnvelope}}
RATE_LIMITED: dict[int | str, dict[str, Any]] = {429: {"model": ErrorEnvelope}}

Config = Annotated[Settings, Depends(get_settings)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
# Admins and the owner. Members get 403.
AdminWorkspace = Annotated[WorkspaceContext, Depends(require_role("admin", path=True))]
OwnerWorkspace = Annotated[WorkspaceContext, Depends(require_role("owner", path=True))]


async def get_workspace_service(
    db: RequestSession, config: Config, limiter: Limiter, client: Client, mail: Mail
) -> WorkspaceService:
    return WorkspaceService(db, config, limiter, client, mail)


Service = Annotated[WorkspaceService, Depends(get_workspace_service)]


def describe(context: WorkspaceContext) -> WorkspaceResponse:
    return WorkspaceResponse.build(context.workspace, context.role)


@router.post("", status_code=status.HTTP_201_CREATED, responses=CONFLICT | RATE_LIMITED)
async def create_workspace(
    data: WorkspaceCreate, user: CurrentUser, service: Service, mutation: Mutation
) -> WorkspaceResponse:
    """Create a workspace; the caller becomes its owner."""
    workspace, role = await service.create(user, data)
    return mutation.save(WorkspaceResponse.build(workspace, role), status.HTTP_201_CREATED)


@router.get("")
async def list_workspaces(
    user: CurrentUser,
    service: Service,
    limit: PageSize = DEFAULT_PAGE_SIZE,
    cursor: PageCursor = None,
) -> WorkspacePage:
    """The workspaces the caller belongs to. Empty until they create or join one."""
    rows, next_cursor = await service.list_for(user, limit, cursor)
    return WorkspacePage(
        items=[WorkspaceResponse.build(workspace, role) for workspace, role in rows],
        next_cursor=next_cursor,
    )


@router.get("/{workspace_id}", responses=NOT_FOUND)
async def get_workspace(context: PathWorkspace) -> WorkspaceResponse:
    return describe(context)


@router.patch("/{workspace_id}", responses=NOT_FOUND | CONFLICT)
async def update_workspace(
    data: WorkspaceUpdate, context: AdminWorkspace, service: Service, mutation: Mutation
) -> WorkspaceResponse:
    workspace = await service.update(context, data)
    return mutation.save(WorkspaceResponse.build(workspace, context.role))


@router.delete(
    "/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND | CONFLICT
)
async def delete_workspace(
    mutation: Mutation, auth: Auth, context: OwnerWorkspace, service: Service
) -> None:
    """Delete the workspace and everything in it. Owner only; needs a recent sign-in."""
    await service.delete(auth, context)
    mutation.save(None, status.HTTP_204_NO_CONTENT)


@router.get("/{workspace_id}/members", responses=NOT_FOUND)
async def list_members(
    context: PathWorkspace,
    service: Service,
    limit: PageSize = DEFAULT_PAGE_SIZE,
    cursor: PageCursor = None,
) -> MemberPage:
    rows, next_cursor = await service.list_members(context, limit, cursor)
    show_email = context.role.at_least(WorkspaceRole.ADMIN)
    return MemberPage(
        items=[member_response(member, user, show_email=show_email) for member, user in rows],
        next_cursor=next_cursor,
    )


@router.patch(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
)
async def change_member_role(
    user_id: uuid.UUID,
    data: RoleUpdate,
    context: OwnerWorkspace,
    service: Service,
    mutation: Mutation,
) -> None:
    """Make a member an admin or a plain member. Owner only; the owner's role never changes."""
    await service.change_role(context, user_id, data.role)
    mutation.save(None, status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
)
async def remove_member(
    user_id: uuid.UUID, context: AdminWorkspace, service: Service, mutation: Mutation
) -> None:
    """Remove a member. Admins remove members; only the owner removes admins."""
    await service.remove_member(context, user_id)
    mutation.save(None, status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
)
async def leave_workspace(mutation: Mutation, context: PathWorkspace, service: Service) -> None:
    """Leave the workspace. The owner must transfer ownership or delete it instead."""
    await service.leave(context)
    mutation.save(None, status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/transfer-ownership",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
)
async def transfer_ownership(
    data: OwnershipTransfer,
    auth: Auth,
    context: OwnerWorkspace,
    service: Service,
    mutation: Mutation,
) -> None:
    """Make another member the owner; the caller becomes an admin. Needs a recent sign-in."""
    await service.transfer_ownership(auth, context, data.user_id)
    mutation.save(None, status.HTTP_204_NO_CONTENT)


@router.post(
    "/{workspace_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND | CONFLICT | RATE_LIMITED,
)
async def create_invitation(
    data: InvitationCreate, context: AdminWorkspace, service: Service
) -> CreatedInvitation:
    """Invite by email, or without an email to get a shareable link (and QR) token.

    The token of a link invitation is returned once, here. This endpoint does not use
    ``Idempotency-Key`` replay: stored responses would keep the token in plain text.
    """
    invitation, token = await service.create_invitation(context, data)
    return CreatedInvitation(
        **InvitationResponse.build(invitation, datetime.now(UTC)).model_dump(),
        token=token,
        link=service.invite_link(token) if token else None,
    )


@router.get("/{workspace_id}/invitations", responses=NOT_FOUND)
async def list_invitations(
    context: AdminWorkspace,
    service: Service,
    limit: PageSize = DEFAULT_PAGE_SIZE,
    cursor: PageCursor = None,
) -> InvitationPage:
    rows, next_cursor = await service.list_invitations(context, limit, cursor)
    now = datetime.now(UTC)
    return InvitationPage(
        items=[InvitationResponse.build(invitation, now) for invitation in rows],
        next_cursor=next_cursor,
    )


@router.delete(
    "/{workspace_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=NOT_FOUND | CONFLICT,
)
async def revoke_invitation(
    invitation_id: uuid.UUID, context: AdminWorkspace, service: Service, mutation: Mutation
) -> None:
    await service.revoke_invitation(context, invitation_id)
    mutation.save(None, status.HTTP_204_NO_CONTENT)


@invitations_router.post("/accept", responses=NOT_FOUND | CONFLICT | RATE_LIMITED)
async def accept_invitation(
    data: InvitationAccept, user: CurrentUser, service: Service, mutation: Mutation
) -> WorkspaceResponse:
    """Join a workspace with an invitation token (from the emailed or shared link).

    404 ``invalid_invitation`` for every unusable token: unknown, expired, revoked,
    already used, or sent to a different email address.
    """
    workspace, role = await service.accept_invitation(user, data.token)
    return mutation.save(WorkspaceResponse.build(workspace, role))
