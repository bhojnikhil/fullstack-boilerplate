"""
Item repository - Example CRUD repository.
This demonstrates the repository pattern for any entity.
"""

import uuid

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Cursor
from app.modules.items.models import Item


class ItemRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(
        self, user_id: uuid.UUID, limit: int, before: Cursor | None
    ) -> list[Item]:
        stmt = select(Item).where(Item.user_id == user_id)
        if before is not None:
            stmt = stmt.where(tuple_(Item.created_at, Item.id) < before)
        stmt = stmt.order_by(Item.created_at.desc(), Item.id.desc()).limit(limit)
        return list(await self._db.scalars(stmt))

    async def get_by_id(self, item_id: uuid.UUID) -> Item | None:
        """Get item by ID."""
        stmt = select(Item).where(Item.id == item_id)
        return await self._db.scalar(stmt)

    async def create(self, user_id: uuid.UUID, title: str, description: str | None = None) -> Item:
        """Create a new item."""
        item = Item(user_id=user_id, title=title, description=description)
        self._db.add(item)
        await self._db.flush()
        await self._db.refresh(item)
        return item

    async def update(
        self,
        item: Item,
        title: str | None = None,
        description: str | None = None,
        is_active: bool | None = None,
    ) -> Item:
        """Update an item."""
        if title is not None:
            item.title = title
        if description is not None:
            item.description = description
        if is_active is not None:
            item.is_active = is_active
        await self._db.flush()
        await self._db.refresh(item)
        return item

    async def delete(self, item: Item) -> None:
        """Delete an item."""
        await self._db.delete(item)
        await self._db.flush()
