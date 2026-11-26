"""Account deletion hook for workspaces (see app.modules.auth.deletion).

A user who owns a workspace that has other members cannot delete their account until
they transfer ownership or delete that workspace: the API answers 409
``account_deletion_blocked`` with ``details.reason == "sole_workspace_owner"`` and the
workspace ids. Workspaces where the user is the only member are deleted with the
account, together with their items and invitations. Memberships elsewhere end with the
user row; the items they created stay in those workspaces without an author.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rls
from app.core.audit import AuditEventType, record_event
from app.modules.auth.deletion import AccountDeletionBlockedError
from app.modules.auth.models import User
from app.modules.workspaces.repository import MemberRepository, WorkspaceRepository


class WorkspaceDeletionHook:
    async def check(self, db: AsyncSession, user: User) -> None:
        shared = [ws for ws, members in await self.owned_with_members(db, user) if members > 1]
        if shared:
            raise AccountDeletionBlockedError(
                "Transfer ownership of your shared workspaces or delete them first",
                {"reason": "sole_workspace_owner", "workspace_ids": [str(ws) for ws in shared]},
            )

    async def before_delete(self, db: AsyncSession, user: User) -> None:
        workspaces = WorkspaceRepository(db)
        for workspace_id, members in await self.owned_with_members(db, user):
            if members > 1:  # pragma: no cover - check() refused these
                raise AccountDeletionBlockedError("A workspace gained members")
            await rls.bind(db, rls.WORKSPACE_ID, str(workspace_id))
            workspace = await workspaces.get(workspace_id)
            if workspace is not None:
                await workspaces.delete(workspace)
                record_event(
                    db,
                    AuditEventType.WORKSPACE_DELETED,
                    user_id=user.id,
                    workspace_id=str(workspace_id),
                    reason="account_deleted",
                )
        await rls.bind(db, rls.WORKSPACE_ID, None)

    async def owned_with_members(self, db: AsyncSession, user: User) -> list[tuple[uuid.UUID, int]]:
        """Each owned workspace, locked in id order, with its member count."""
        workspaces = WorkspaceRepository(db)
        result: list[tuple[uuid.UUID, int]] = []
        for workspace_id in await workspaces.owned_ids(user.id):
            await rls.bind(db, rls.WORKSPACE_ID, str(workspace_id))
            if await workspaces.lock(workspace_id) is None:  # pragma: no cover - just listed
                continue
            result.append((workspace_id, await MemberRepository(db, workspace_id).count()))
        await rls.bind(db, rls.WORKSPACE_ID, None)
        return result
