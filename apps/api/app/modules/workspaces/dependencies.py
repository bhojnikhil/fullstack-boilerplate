"""Resolve and authorize the active workspace.

Workspace-scoped routes depend on ``Workspace`` (the ``X-Workspace-Id`` header: domain
data such as items) or ``PathWorkspace`` (``/v1/workspaces/{workspace_id}/...``: managing
the workspace itself). Both prove the caller is a member and answer 404 otherwise, so a
workspace that exists but belongs to someone else looks the same as one that does not.
The proof also sets ``app.workspace_id`` for row-level security.
"""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.db import RequestSession
from app.core.errors import DomainError, ErrorCode
from app.modules.auth.dependencies import CurrentUser
from app.modules.auth.models import User
from app.modules.workspaces.models import Workspace, WorkspaceRole
from app.modules.workspaces.repository import WorkspaceRepository

WORKSPACE_HEADER = "X-Workspace-Id"


@dataclass(frozen=True)
class WorkspaceContext:
    user: User
    workspace: Workspace
    role: WorkspaceRole


async def resolve_workspace(
    request: Request, db: RequestSession, user: User, workspace_id: uuid.UUID
) -> WorkspaceContext:
    repository = WorkspaceRepository(db)
    role = await repository.authorize(user.id, workspace_id)
    workspace = await repository.get(workspace_id) if role is not None else None
    if role is None or workspace is None:
        raise DomainError(ErrorCode.WORKSPACE_NOT_FOUND)
    request.state.workspace_id = str(workspace.id)
    return WorkspaceContext(user, workspace, role)


async def get_header_workspace(
    request: Request,
    db: RequestSession,
    user: CurrentUser,
    workspace_header: Annotated[
        str | None,
        Header(
            alias=WORKSPACE_HEADER,
            description="The active workspace. 404 unless the caller is a member.",
        ),
    ] = None,
) -> WorkspaceContext:
    if not workspace_header:
        raise DomainError(ErrorCode.WORKSPACE_REQUIRED)
    try:
        workspace_id = uuid.UUID(workspace_header)
    except ValueError:
        # The same answer as for a workspace that does not exist.
        raise DomainError(ErrorCode.WORKSPACE_NOT_FOUND) from None
    return await resolve_workspace(request, db, user, workspace_id)


async def get_path_workspace(
    request: Request, db: RequestSession, user: CurrentUser, workspace_id: uuid.UUID
) -> WorkspaceContext:
    return await resolve_workspace(request, db, user, workspace_id)


# Routes whose dependency tree contains one of these are workspace-scoped. The tenant
# isolation tests discover routes through this set.
WORKSPACE_RESOLVERS = frozenset({get_header_workspace, get_path_workspace})

ActiveWorkspace = Annotated[WorkspaceContext, Depends(get_header_workspace)]
PathWorkspace = Annotated[WorkspaceContext, Depends(get_path_workspace)]


def require_role(
    minimum: str | WorkspaceRole, *, path: bool = False
) -> Callable[..., Awaitable[WorkspaceContext]]:
    """A dependency that admits members with at least ``minimum`` and answers 403
    otherwise. Members already know the workspace exists, so 403 reveals nothing.

    ``Annotated[WorkspaceContext, Depends(require_role("admin"))]`` uses the
    ``X-Workspace-Id`` header; ``path=True`` uses the ``workspace_id`` path parameter.
    """
    required = WorkspaceRole(minimum)
    resolver = get_path_workspace if path else get_header_workspace

    async def dependency(
        context: Annotated[WorkspaceContext, Depends(resolver)],
    ) -> WorkspaceContext:
        if not context.role.at_least(required):
            raise DomainError(ErrorCode.INSUFFICIENT_ROLE)
        return context

    return dependency
