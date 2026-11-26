"""Workspaces (tenants), their members and invitations.

Every table here is a tenant table with row-level security (migration 0005).

One owner per workspace is enforced by the database, not just the service:

- ``uq_memberships_one_owner`` allows at most one ``owner`` membership per workspace;
- ``workspaces`` points at its owner's membership through the deferred composite foreign
  key ``(id, owner_id, owner_role) -> memberships(workspace_id, user_id, role)`` where
  ``owner_role`` is always ``'owner'``. At commit the workspace must therefore have an
  owner membership, and that membership cannot be deleted or demoted without naming a
  new owner in the same transaction.

The two tables reference each other, so rows are inserted in separate flushes: the
workspace first (the key is deferred), then the owner's membership.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

    @property
    def rank(self) -> int:
        return {"owner": 3, "admin": 2, "member": 1}[self.value]

    def at_least(self, minimum: "WorkspaceRole") -> bool:
        return self.rank >= minimum.rank


class InvitableRole(StrEnum):
    """Roles an invitation can grant. Ownership moves only by transfer."""

    ADMIN = "admin"
    MEMBER = "member"


class Workspace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces"
    __table_args__ = (
        ForeignKeyConstraint(
            ["id", "owner_id", "owner_role"],
            ["memberships.workspace_id", "memberships.user_id", "memberships.role"],
            name="fk_workspaces_owner_membership",
            deferrable=True,
            initially="DEFERRED",
            use_alter=True,
        ),
        CheckConstraint("owner_role = 'owner'", name="ck_workspaces_owner_role"),
    )
    __mapper_args__ = {"eager_defaults": True}

    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(48), unique=True)
    # ISO 4217 code and IANA zone. Money is stored as integer minor units in this
    # currency; calendar dates are interpreted in this zone.
    currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64))
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    owner_role: Mapped[str] = mapped_column(
        String(5), server_default=text("'owner'"), default=WorkspaceRole.OWNER.value
    )


class Membership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("workspace_id", "user_id", name="uq_memberships_workspace_user"),
        # The target of workspaces' owner foreign key.
        UniqueConstraint(
            "workspace_id", "user_id", "role", name="uq_memberships_workspace_user_role"
        ),
        Index(
            "uq_memberships_one_owner",
            "workspace_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
        Index("ix_memberships_user_id", "user_id"),
        CheckConstraint("role IN ('owner', 'admin', 'member')", name="ck_memberships_role"),
    )
    __mapper_args__ = {"eager_defaults": True}

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    role: Mapped[WorkspaceRole] = mapped_column(String(16))


class Invitation(Base, UUIDMixin, TimestampMixin):
    """A single-use invitation. ``email`` set: only that verified address can accept.
    ``email`` empty: a shareable link or QR code; whoever opens it first joins."""

    __tablename__ = "invitations"
    __table_args__ = (
        Index("ix_invitations_workspace_created_id", "workspace_id", "created_at", "id"),
        CheckConstraint("role IN ('admin', 'member')", name="ck_invitations_role"),
        CheckConstraint(
            "accepted_at IS NULL OR revoked_at IS NULL", name="ck_invitations_one_outcome"
        ),
    )
    __mapper_args__ = {"eager_defaults": True}

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE")
    )
    email: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[InvitableRole] = mapped_column(String(16))
    # SHA-256 of the opaque token; the token itself is never stored.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
