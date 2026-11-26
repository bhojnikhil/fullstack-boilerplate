"""Workspace persistence. Repositories add, flush and query; they never commit.

Locking order for anything that changes membership: the user row (when a user is added
or deleted), then the workspace row, then membership or invitation rows. Mutating flows
lock the workspace first (``lock``) so they serialize per workspace.

``WorkspaceRepository`` and ``InvitationTokenRepository`` are the only classes that
look across workspaces: the first by user (the workspaces a user belongs to), the second
by invitation token. Everything else needs a workspace id (``TenantRepository``).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import String, cast, func, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Cursor
from app.core.tenancy import TenantRepository
from app.modules.auth.models import User
from app.modules.workspaces.models import (
    InvitableRole,
    Invitation,
    Membership,
    Workspace,
    WorkspaceRole,
)


class WorkspaceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def authorize(self, user_id: uuid.UUID, workspace_id: uuid.UUID) -> WorkspaceRole | None:
        """The user's role in the workspace, or None. On success the same statement sets
        ``app.workspace_id`` for the rest of the transaction: the setting exists only
        for workspaces the user belongs to. Not-a-member and no-such-workspace are the
        same empty result."""
        stmt = select(
            Membership.role,
            func.set_config("app.workspace_id", cast(Membership.workspace_id, String), True),
        ).where(Membership.user_id == user_id, Membership.workspace_id == workspace_id)
        row = (await self._db.execute(stmt)).one_or_none()
        return WorkspaceRole(row[0]) if row is not None else None

    async def get(self, workspace_id: uuid.UUID) -> Workspace | None:
        return await self._db.get(Workspace, workspace_id)

    async def lock(self, workspace_id: uuid.UUID) -> Workspace | None:
        """Lock the workspace row and reload it, so checks see the latest committed state."""
        stmt = (
            select(Workspace)
            .where(Workspace.id == workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self._db.scalar(stmt)

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int, before: Cursor | None
    ) -> list[tuple[Workspace, WorkspaceRole]]:
        stmt = (
            select(Workspace, Membership.role)
            .join(Membership, Membership.workspace_id == Workspace.id)
            .where(Membership.user_id == user_id)
        )
        if before is not None:
            stmt = stmt.where(tuple_(Workspace.created_at, Workspace.id) < before)
        stmt = stmt.order_by(Workspace.created_at.desc(), Workspace.id.desc()).limit(limit)
        return [
            (workspace, WorkspaceRole(role)) for workspace, role in await self._db.execute(stmt)
        ]

    async def owned_ids(self, user_id: uuid.UUID) -> list[uuid.UUID]:
        """Workspaces the user owns, in the order they must be locked."""
        stmt = (
            select(Membership.workspace_id)
            .where(Membership.user_id == user_id, Membership.role == WorkspaceRole.OWNER)
            .order_by(Membership.workspace_id)
        )
        return list(await self._db.scalars(stmt))

    async def create(
        self,
        workspace_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        name: str,
        slug: str,
        currency: str,
        timezone: str,
    ) -> Workspace | None:
        """Insert a workspace and its owner's membership. None if the slug is taken.

        The owner key is deferred, so the workspace goes in first and the membership in
        a second statement; the database checks the pair when the transaction commits.
        """
        stmt = (
            insert(Workspace)
            .values(
                id=workspace_id,
                name=name,
                slug=slug,
                currency=currency,
                timezone=timezone,
                owner_id=owner_id,
            )
            .on_conflict_do_nothing(index_elements=[Workspace.slug])
            .returning(Workspace)
        )
        workspace = await self._db.scalar(stmt)
        if workspace is None:
            return None
        self._db.add(
            Membership(workspace_id=workspace_id, user_id=owner_id, role=WorkspaceRole.OWNER)
        )
        await self._db.flush()
        return workspace

    async def change(
        self,
        workspace: Workspace,
        *,
        name: str | None,
        slug: str | None,
        currency: str | None,
        timezone: str | None,
    ) -> bool:
        """Apply the given fields. False if the new slug belongs to another workspace.

        Row-level security hides other workspaces from this role, so the unique index
        is the only way to learn that a slug is taken.
        """
        try:
            async with self._db.begin_nested():
                if name is not None:
                    workspace.name = name
                if slug is not None:
                    workspace.slug = slug
                if currency is not None:
                    workspace.currency = currency
                if timezone is not None:
                    workspace.timezone = timezone
                await self._db.flush()
        except IntegrityError:
            return False
        await self._db.refresh(workspace)
        return True

    async def delete(self, workspace: Workspace) -> None:
        await self._db.delete(workspace)
        await self._db.flush()


class MemberRepository(TenantRepository):
    async def list_page(self, limit: int, before: Cursor | None) -> list[tuple[Membership, User]]:
        stmt = (
            select(Membership, User)
            .join(User, User.id == Membership.user_id)
            .where(Membership.workspace_id == self.workspace_id)
        )
        if before is not None:
            stmt = stmt.where(tuple_(Membership.created_at, Membership.id) < before)
        stmt = stmt.order_by(Membership.created_at.desc(), Membership.id.desc()).limit(limit)
        return [(membership, user) for membership, user in await self._db.execute(stmt)]

    async def get(self, user_id: uuid.UUID) -> Membership | None:
        stmt = (
            select(Membership)
            .where(Membership.workspace_id == self.workspace_id, Membership.user_id == user_id)
            .execution_options(populate_existing=True)
        )
        return await self._db.scalar(stmt)

    async def count(self) -> int:
        stmt = select(func.count()).where(Membership.workspace_id == self.workspace_id)
        return int(await self._db.scalar(stmt) or 0)

    async def add(self, user_id: uuid.UUID, role: WorkspaceRole) -> Membership:
        membership = Membership(workspace_id=self.workspace_id, user_id=user_id, role=role)
        self._db.add(membership)
        await self._db.flush()
        return membership

    async def delete(self, membership: Membership) -> None:
        await self._db.delete(membership)
        await self._db.flush()


class InvitationRepository(TenantRepository):
    async def add(
        self,
        *,
        email: str | None,
        role: InvitableRole,
        token_hash: str,
        expires_at: datetime,
        invited_by_id: uuid.UUID,
    ) -> Invitation:
        invitation = Invitation(
            workspace_id=self.workspace_id,
            email=email,
            role=role,
            token_hash=token_hash,
            expires_at=expires_at,
            invited_by_id=invited_by_id,
        )
        self._db.add(invitation)
        await self._db.flush()
        return invitation

    async def list_page(self, limit: int, before: Cursor | None) -> list[Invitation]:
        stmt = select(Invitation).where(Invitation.workspace_id == self.workspace_id)
        if before is not None:
            stmt = stmt.where(tuple_(Invitation.created_at, Invitation.id) < before)
        stmt = stmt.order_by(Invitation.created_at.desc(), Invitation.id.desc()).limit(limit)
        return list(await self._db.scalars(stmt))

    async def lock(self, invitation_id: uuid.UUID) -> Invitation | None:
        stmt = (
            select(Invitation)
            .where(Invitation.workspace_id == self.workspace_id, Invitation.id == invitation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self._db.scalar(stmt)

    async def pending_for_email(self, email: str) -> list[Invitation]:
        stmt = (
            select(Invitation)
            .where(
                Invitation.workspace_id == self.workspace_id,
                func.lower(Invitation.email) == email.lower(),
                Invitation.accepted_at.is_(None),
                Invitation.revoked_at.is_(None),
            )
            .order_by(Invitation.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(await self._db.scalars(stmt))


class InvitationTokenRepository:
    """Finds an invitation by token digest. Row-level security shows an invitation to
    someone outside its workspace only while ``app.invitation_hash`` equals its digest."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def find(self, token_hash: str) -> Invitation | None:
        stmt = select(Invitation).where(Invitation.token_hash == token_hash)
        return await self._db.scalar(stmt)

    async def lock(self, invitation_id: uuid.UUID) -> Invitation | None:
        stmt = (
            select(Invitation)
            .where(Invitation.id == invitation_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return await self._db.scalar(stmt)


def is_pending(invitation: Invitation) -> bool:
    return (
        invitation.accepted_at is None
        and invitation.revoked_at is None
        and invitation.expires_at > datetime.now(UTC)
    )
