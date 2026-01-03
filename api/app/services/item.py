"""
Item service - Example CRUD business logic.
Demonstrates the service pattern for any domain entity.
"""

import uuid

from fastapi import HTTPException, status

from app.models.item import Item
from app.repositories.item import ItemRepository
from app.schemas.item import ItemCreate, ItemUpdate


class ItemService:
    def __init__(self, repository: ItemRepository) -> None:
        self._repository = repository

    def get_user_items(self, user_id: uuid.UUID) -> list[Item]:
        """Get all items for a user."""
        return self._repository.get_all_for_user(user_id)

    def get_item(self, item_id: uuid.UUID, user_id: uuid.UUID) -> Item:
        """Get single item by ID, with authorization check."""
        item = self._repository.get_by_id(item_id)
        if item is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Item not found",
            )

        # Authorization: user can only access their own items
        if item.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to access this item",
            )

        return item

    def create_item(self, user_id: uuid.UUID, data: ItemCreate) -> Item:
        """Create a new item for user."""
        return self._repository.create(
            user_id=user_id,
            title=data.title,
            description=data.description,
        )

    def update_item(
        self, item_id: uuid.UUID, user_id: uuid.UUID, data: ItemUpdate
    ) -> Item:
        """Update an item, with authorization check."""
        item = self.get_item(item_id, user_id)  # Validates ownership
        return self._repository.update(
            item=item,
            title=data.title,
            description=data.description,
            is_active=data.is_active,
        )

    def delete_item(self, item_id: uuid.UUID, user_id: uuid.UUID) -> None:
        """Delete an item, with authorization check."""
        item = self.get_item(item_id, user_id)  # Validates ownership
        self._repository.delete(item)
