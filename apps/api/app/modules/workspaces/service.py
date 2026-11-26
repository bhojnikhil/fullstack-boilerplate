"""Workspace, membership and invitation rules.

Roles: ``owner`` > ``admin`` > ``member``.

==================================  =======  =====  ======
Action                              owner    admin  member
==================================  =======  =====  ======
read workspace, list members        yes      yes    yes
update name, slug, currency, zone   yes      yes    no
list, create, revoke invitations    yes      yes    no
invite as ``admin``                 yes      no     no
remove a member                     yes      yes    no
remove an admin                     yes      no     no
change a member's role              yes      no     no
transfer ownership, delete          yes      no     no
leave                               no       yes    yes
==================================  =======  =====  ======

Exactly one owner: the service checks it under the workspace lock and the database
enforces it (see ``models``). Every mutation locks in the same order, user row (when
one is added), workspace row, then membership or invitation rows, so concurrent
requests wait for each other instead of deadlocking.
"""

import secrets
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rls
from app.core.audit import AuditEventType, record_event
from app.core.client import ClientInfo
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.core.pagination import Cursor, decode_cursor, encode_cursor
from app.core.ratelimit import RateLimiter
from app.core.security import new_token, token_digest
from app.integrations.email import MailSender
from app.integrations.email.templates import Template
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.models import User
from app.modules.auth.repository import UserRepository
from app.modules.auth.service import describe, web_link
from app.modules.auth.sessions import require_recent_authentication
from app.modules.workspaces import limits
from app.modules.workspaces.dependencies import WorkspaceContext
from app.modules.workspaces.models import (
    InvitableRole,
    Invitation,
    Membership,
    Workspace,
    WorkspaceRole,
)
from app.modules.workspaces.repository import (
    InvitationRepository,
    InvitationTokenRepository,
    MemberRepository,
    WorkspaceRepository,
)
from app.modules.workspaces.schemas import (
    InvitationCreate,
    WorkspaceCreate,
    WorkspaceUpdate,
)
from app.modules.workspaces.validation import slugify

INVITE_PATH = "/invite"
MAX_OWNED_WORKSPACES = 20
SLUG_ATTEMPTS = 5


def page[T](
    rows: list[T], limit: int, position: Callable[[T], Cursor]
) -> tuple[list[T], str | None]:
    if len(rows) <= limit:
        return rows, None
    return rows[:limit], encode_cursor(position(rows[limit - 1]))


class WorkspaceService:
    def __init__(
        self,
        db: AsyncSession,
        config: Settings,
        limiter: RateLimiter,
        client: ClientInfo,
        mail: MailSender,
    ) -> None:
        self.db = db
        self.config = config
        self.limiter = limiter
        self.client = client
        self.mail = mail
        self.workspaces = WorkspaceRepository(db)
        self.users = UserRepository(db)

    def audit(
        self, event: AuditEventType, actor: uuid.UUID, **details: str | int | bool | None
    ) -> None:
        # mypy reads **details as possible values for record_event's own parameters.
        record_event(self.db, event, client=self.client, user_id=actor, **details)  # type: ignore[arg-type]

    # --- workspaces -------------------------------------------------------------------

    async def create(self, user: User, data: WorkspaceCreate) -> tuple[Workspace, WorkspaceRole]:
        await self.limiter.hit(limits.WORKSPACE_CREATE_PER_ACCOUNT, str(user.id))
        # The user row serializes the ownership cap for one user.
        await self.users.lock(user.id)
        if len(await self.workspaces.owned_ids(user.id)) >= MAX_OWNED_WORKSPACES:
            raise DomainError(ErrorCode.WORKSPACE_LIMIT_REACHED)

        workspace_id = uuid.uuid4()
        # The workspace is brand new: the creator may write it before any membership exists.
        await rls.bind(self.db, rls.WORKSPACE_ID, str(workspace_id))
        workspace: Workspace | None = None
        # A generated slug is retried on the rare collision; a chosen one is not.
        for _ in range(1 if data.slug else SLUG_ATTEMPTS):
            workspace = await self.workspaces.create(
                workspace_id,
                user.id,
                name=data.name,
                slug=data.slug or f"{slugify(data.name)}-{secrets.token_hex(3)}",
                currency=data.currency,
                timezone=data.timezone,
            )
            if workspace is not None:
                break
        if workspace is None:
            raise DomainError(ErrorCode.WORKSPACE_SLUG_TAKEN)
        self.audit(AuditEventType.WORKSPACE_CREATED, user.id, workspace_id=str(workspace.id))
        return workspace, WorkspaceRole.OWNER

    async def list_for(
        self, user: User, limit: int, cursor: str | None
    ) -> tuple[list[tuple[Workspace, WorkspaceRole]], str | None]:
        before: Cursor | None = decode_cursor(cursor) if cursor is not None else None
        rows = await self.workspaces.list_for_user(user.id, limit + 1, before)
        return page(rows, limit, lambda row: (row[0].created_at, row[0].id))

    async def update(self, context: WorkspaceContext, data: WorkspaceUpdate) -> Workspace:
        workspace = await self.locked(context)
        changed = await self.workspaces.change(
            workspace,
            name=data.name,
            slug=data.slug,
            currency=data.currency,
            timezone=data.timezone,
        )
        if not changed:
            raise DomainError(ErrorCode.WORKSPACE_SLUG_TAKEN)
        return workspace

    async def delete(self, auth: AuthContext, context: WorkspaceContext) -> None:
        require_recent_authentication(auth.session, self.config)
        workspace = await self.locked(context)
        await self.workspaces.delete(workspace)
        self.audit(
            AuditEventType.WORKSPACE_DELETED, context.user.id, workspace_id=str(workspace.id)
        )

    async def locked(self, context: WorkspaceContext) -> Workspace:
        workspace = await self.workspaces.lock(context.workspace.id)
        if workspace is None:  # Deleted since the request authorized it.
            raise DomainError(ErrorCode.WORKSPACE_NOT_FOUND)
        return workspace

    # --- members ----------------------------------------------------------------------

    async def list_members(
        self, context: WorkspaceContext, limit: int, cursor: str | None
    ) -> tuple[list[tuple[Membership, User]], str | None]:
        before: Cursor | None = decode_cursor(cursor) if cursor is not None else None
        rows = await MemberRepository(self.db, context.workspace.id).list_page(limit + 1, before)
        return page(rows, limit, lambda row: (row[0].created_at, row[0].id))

    async def change_role(
        self, context: WorkspaceContext, user_id: uuid.UUID, role: InvitableRole
    ) -> None:
        await self.locked(context)
        member = await MemberRepository(self.db, context.workspace.id).get(user_id)
        if member is None:
            raise DomainError(ErrorCode.MEMBER_NOT_FOUND)
        if member.role == WorkspaceRole.OWNER:
            raise DomainError(ErrorCode.OWNER_PROTECTED)
        previous = member.role
        member.role = WorkspaceRole(role)
        await self.db.flush()
        self.audit(
            AuditEventType.MEMBER_ROLE_CHANGED,
            context.user.id,
            workspace_id=str(context.workspace.id),
            target_user_id=str(user_id),
            from_role=previous,
            to_role=role,
        )

    async def remove_member(self, context: WorkspaceContext, user_id: uuid.UUID) -> None:
        await self.locked(context)
        members = MemberRepository(self.db, context.workspace.id)
        member = await members.get(user_id)
        if member is None:
            raise DomainError(ErrorCode.MEMBER_NOT_FOUND)
        if member.role == WorkspaceRole.OWNER:
            raise DomainError(ErrorCode.OWNER_PROTECTED)
        # Admins manage members; only the owner manages admins.
        if member.role == WorkspaceRole.ADMIN and context.role != WorkspaceRole.OWNER:
            raise DomainError(ErrorCode.INSUFFICIENT_ROLE)
        await members.delete(member)
        self.audit(
            AuditEventType.MEMBER_REMOVED,
            context.user.id,
            workspace_id=str(context.workspace.id),
            target_user_id=str(user_id),
            role=member.role,
        )

    async def leave(self, context: WorkspaceContext) -> None:
        await self.locked(context)
        members = MemberRepository(self.db, context.workspace.id)
        member = await members.get(context.user.id)
        if member is None:  # Removed since the request authorized it.
            raise DomainError(ErrorCode.WORKSPACE_NOT_FOUND)
        if member.role == WorkspaceRole.OWNER:
            raise DomainError(ErrorCode.OWNER_CANNOT_LEAVE)
        await members.delete(member)
        self.audit(
            AuditEventType.MEMBER_LEFT, context.user.id, workspace_id=str(context.workspace.id)
        )

    async def transfer_ownership(
        self, auth: AuthContext, context: WorkspaceContext, new_owner_id: uuid.UUID
    ) -> None:
        require_recent_authentication(auth.session, self.config)
        workspace = await self.locked(context)
        members = MemberRepository(self.db, workspace.id)
        current = await members.get(context.user.id)
        target = await members.get(new_owner_id)
        if current is None or current.role != WorkspaceRole.OWNER:
            raise DomainError(ErrorCode.INSUFFICIENT_ROLE)
        if target is None:
            raise DomainError(ErrorCode.MEMBER_NOT_FOUND)
        if target.id == current.id:
            raise DomainError(ErrorCode.OWNER_PROTECTED, "You already own this workspace")
        # One owner at every step: the unique index allows a single owner row, and the
        # deferred owner key is checked against the final state at commit.
        current.role = WorkspaceRole.ADMIN
        await self.db.flush()
        target.role = WorkspaceRole.OWNER
        await self.db.flush()
        workspace.owner_id = target.user_id
        await self.db.flush()
        self.audit(
            AuditEventType.OWNERSHIP_TRANSFERRED,
            context.user.id,
            workspace_id=str(workspace.id),
            new_owner_id=str(new_owner_id),
        )

    # --- invitations ------------------------------------------------------------------

    async def create_invitation(
        self, context: WorkspaceContext, data: InvitationCreate
    ) -> tuple[Invitation, str | None]:
        """Create an invitation. Returns the token only for link invitations."""
        if data.role == InvitableRole.ADMIN and context.role != WorkspaceRole.OWNER:
            raise DomainError(ErrorCode.INSUFFICIENT_ROLE)
        await self.limiter.hit(limits.INVITE_PER_IP, self.client.ip)
        await self.limiter.hit(limits.INVITE_PER_ACCOUNT, str(context.user.id))
        await self.limiter.hit(limits.INVITE_PER_WORKSPACE, str(context.workspace.id))

        workspace = await self.locked(context)
        invitations = InvitationRepository(self.db, workspace.id)
        if data.email is not None:
            invited = await self.users.get_by_email(data.email)
            if invited is not None and await MemberRepository(self.db, workspace.id).get(
                invited.id
            ):
                raise DomainError(ErrorCode.ALREADY_MEMBER)
            # Only the newest invitation to an address stays usable.
            for previous in await invitations.pending_for_email(data.email):
                previous.revoked_at = datetime.now(UTC)
                self.audit(
                    AuditEventType.INVITATION_REVOKED,
                    context.user.id,
                    workspace_id=str(workspace.id),
                    invitation_id=str(previous.id),
                    reason="replaced",
                )

        lifetime = timedelta(days=self.config.invitation_expire_days)
        token = new_token()
        invitation = await invitations.add(
            email=data.email,
            role=data.role,
            token_hash=token_digest(token),
            expires_at=datetime.now(UTC) + lifetime,
            invited_by_id=context.user.id,
        )
        self.audit(
            AuditEventType.INVITATION_CREATED,
            context.user.id,
            workspace_id=str(workspace.id),
            invitation_id=str(invitation.id),
            role=data.role,
            kind="email" if data.email else "link",
        )
        if data.email is None:
            return invitation, token
        self.mail.send(
            Template.WORKSPACE_INVITATION,
            data.email,
            inviter=context.user.name,
            workspace=workspace.name,
            role=data.role,
            link=self.invite_link(token),
            expires=describe(lifetime),
        )
        return invitation, None

    def invite_link(self, token: str) -> str:
        return web_link(self.config, INVITE_PATH, token)

    async def list_invitations(
        self, context: WorkspaceContext, limit: int, cursor: str | None
    ) -> tuple[list[Invitation], str | None]:
        before: Cursor | None = decode_cursor(cursor) if cursor is not None else None
        rows = await InvitationRepository(self.db, context.workspace.id).list_page(
            limit + 1, before
        )
        return page(rows, limit, lambda row: (row.created_at, row.id))

    async def revoke_invitation(self, context: WorkspaceContext, invitation_id: uuid.UUID) -> None:
        invitation = await InvitationRepository(self.db, context.workspace.id).lock(invitation_id)
        if invitation is None:
            raise DomainError(ErrorCode.INVITATION_NOT_FOUND)
        if invitation.accepted_at is not None:
            raise DomainError(ErrorCode.INVITATION_NOT_PENDING)
        if invitation.revoked_at is not None:
            return
        invitation.revoked_at = datetime.now(UTC)
        await self.db.flush()
        self.audit(
            AuditEventType.INVITATION_REVOKED,
            context.user.id,
            workspace_id=str(context.workspace.id),
            invitation_id=str(invitation.id),
            reason="revoked",
        )

    async def accept_invitation(self, user: User, token: str) -> tuple[Workspace, WorkspaceRole]:
        """Join the workspace an invitation names.

        Every way an invitation can be unusable (unknown, expired, revoked, already used,
        meant for another address) answers the same ``invalid_invitation``.
        """
        await self.limiter.hit(limits.INVITE_ACCEPT_PER_IP, self.client.ip)
        await self.limiter.hit(limits.INVITE_ACCEPT_PER_ACCOUNT, str(user.id))
        # Unverified accounts cannot sign in; this keeps invitations from becoming a way around it.
        if user.email_verified_at is None:
            raise DomainError(ErrorCode.EMAIL_VERIFICATION_REQUIRED)

        tokens = InvitationTokenRepository(self.db)
        await rls.bind(self.db, rls.INVITATION_HASH, token_digest(token))
        found = await tokens.find(token_digest(token))
        if found is None:
            raise DomainError(ErrorCode.INVALID_INVITATION)

        # Same order as every other flow: user, workspace, then the invitation row.
        locked_user = await self.users.lock(user.id)
        await rls.bind(self.db, rls.WORKSPACE_ID, str(found.workspace_id))
        workspace = await self.workspaces.lock(found.workspace_id)
        invitation = await tokens.lock(found.id)
        if locked_user is None or workspace is None or invitation is None:
            raise DomainError(ErrorCode.INVALID_INVITATION)
        usable = (
            invitation.accepted_at is None
            and invitation.revoked_at is None
            and invitation.expires_at > datetime.now(UTC)
            and (invitation.email is None or invitation.email.lower() == locked_user.email.lower())
        )
        if not usable:
            raise DomainError(ErrorCode.INVALID_INVITATION)

        members = MemberRepository(self.db, workspace.id)
        if await members.get(locked_user.id) is not None:
            raise DomainError(ErrorCode.ALREADY_MEMBER)
        role = WorkspaceRole(invitation.role)
        await members.add(locked_user.id, role)
        invitation.accepted_at = datetime.now(UTC)
        invitation.accepted_by_id = locked_user.id
        await self.db.flush()
        self.audit(
            AuditEventType.INVITATION_ACCEPTED,
            locked_user.id,
            workspace_id=str(workspace.id),
            invitation_id=str(invitation.id),
            role=role,
        )
        return workspace, role
