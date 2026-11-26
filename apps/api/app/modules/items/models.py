"""
Item model - Example workspace-scoped CRUD entity.
Replace this with your domain entity (Product, Post, Todo, etc.). It shows the tenant
pattern: a ``workspace_id`` column, an index that starts with it, and row-level security
in the migration that created it.
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models import Base, TimestampMixin, UUIDMixin


class Item(Base, UUIDMixin, TimestampMixin):
    """
    Simple item model to demonstrate CRUD patterns.
    This is an example - replace with your domain entity.
    """

    __tablename__ = "items"
    __table_args__ = (Index("ix_items_workspace_created_id", "workspace_id", "created_at", "id"),)

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    # Kept when the author leaves or deletes their account: the item belongs to the workspace.
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
