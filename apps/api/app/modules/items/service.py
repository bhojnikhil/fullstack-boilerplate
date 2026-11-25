"""Item business logic."""

import uuid

from app.core.errors import DomainError, ErrorCode
from app.core.pagination import Cursor, decode_cursor, encode_cursor
from app.modules.items.models import Item
from app.modules.items.repository import ItemRepository
from app.modules.items.schemas import ItemCreate, ItemUpdate


class ItemService:
    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    async def get_user_items(
        self, user_id: uuid.UUID, limit: int, cursor: str | None
    ) -> tuple[list[Item], str | None]:
        before: Cursor | None = decode_cursor(cursor) if cursor is not None else None
        items = await self._repository.list_for_user(user_id, limit + 1, before)
        if len(items) <= limit:
            return items, None
        last = items[limit - 1]
        return items[:limit], encode_cursor((last.created_at, last.id))

    async def get_item(self, item_id: uuid.UUID, user_id: uuid.UUID) -> Item:
        item = await self._repository.get_by_id(item_id)
        if item is None:
            raise DomainError(ErrorCode.ITEM_NOT_FOUND)
        if item.user_id != user_id:
            raise DomainError(ErrorCode.ITEM_FORBIDDEN)

        return item

    async def create_item(self, user_id: uuid.UUID, data: ItemCreate) -> Item:
        return await self._repository.create(
            user_id=user_id,
            title=data.title,
            description=data.description,
        )

    async def update_item(self, item_id: uuid.UUID, user_id: uuid.UUID, data: ItemUpdate) -> Item:
        item = await self.get_item(item_id, user_id)
        return await self._repository.update(
            item=item,
            title=data.title,
            description=data.description,
            is_active=data.is_active,
        )

    async def delete_item(self, item_id: uuid.UUID, user_id: uuid.UUID) -> None:
        item = await self.get_item(item_id, user_id)
        await self._repository.delete(item)
