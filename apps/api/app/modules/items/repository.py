"""
Item repository - Example workspace-scoped repository.
Every query is filtered by the workspace the repository was built for; there is no
method that reads items across workspaces (see app.core.tenancy).
"""

import uuid

from sqlalchemy import select, tuple_

from app.core.pagination import Cursor
from app.core.tenancy import TenantRepository
from app.modules.items.models import Item


class ItemRepository(TenantRepository):
    async def list_page(self, limit: int, before: Cursor | None) -> list[Item]:
        stmt = select(Item).where(Item.workspace_id == self.workspace_id)
        if before is not None:
            stmt = stmt.where(tuple_(Item.created_at, Item.id) < before)
        stmt = stmt.order_by(Item.created_at.desc(), Item.id.desc()).limit(limit)
        return list(await self._db.scalars(stmt))

    async def get_by_id(self, item_id: uuid.UUID) -> Item | None:
        stmt = select(Item).where(Item.workspace_id == self.workspace_id, Item.id == item_id)
        return await self._db.scalar(stmt)

    async def create(
        self, created_by_id: uuid.UUID, title: str, description: str | None = None
    ) -> Item:
        item = Item(
            workspace_id=self.workspace_id,
            created_by_id=created_by_id,
            title=title,
            description=description,
        )
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
        await self._db.delete(item)
        await self._db.flush()
