"""
Item repository - Example CRUD repository.
This demonstrates the repository pattern for any entity.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.item import Item


class ItemRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_all_for_user(self, user_id: uuid.UUID) -> list[Item]:
        """Get all items for a user."""
        stmt = select(Item).where(Item.user_id == user_id).order_by(Item.created_at.desc())
        return list(self._db.execute(stmt).scalars().all())

    def get_by_id(self, item_id: uuid.UUID) -> Item | None:
        """Get item by ID."""
        stmt = select(Item).where(Item.id == item_id)
        return self._db.execute(stmt).scalar_one_or_none()

    def create(self, user_id: uuid.UUID, title: str, description: str | None = None) -> Item:
        """Create a new item."""
        item = Item(user_id=user_id, title=title, description=description)
        self._db.add(item)
        self._db.commit()
        self._db.refresh(item)
        return item

    def update(
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
        self._db.commit()
        self._db.refresh(item)
        return item

    def delete(self, item: Item) -> None:
        """Delete an item."""
        self._db.delete(item)
        self._db.commit()
