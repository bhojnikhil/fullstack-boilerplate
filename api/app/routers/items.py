"""
Item CRUD API routes - Example domain entity endpoints.
Replace 'items' with your domain entity routes.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_active_user
from app.core.db import get_db
from app.models import User
from app.repositories.item import ItemRepository
from app.schemas.item import ItemCreate, ItemResponse, ItemUpdate
from app.services.item import ItemService

router = APIRouter(prefix="/items", tags=["items"])


def get_item_service(db: Session = Depends(get_db)) -> ItemService:
    """Dependency to get ItemService instance."""
    repository = ItemRepository(db)
    return ItemService(repository)


@router.get("", response_model=list[ItemResponse])
def list_items(
    current_user: User = Depends(get_current_active_user),
    service: ItemService = Depends(get_item_service),
) -> list[ItemResponse]:
    """
    Get all items for the current user.

    Requires authentication.
    """
    items = service.get_user_items(current_user.id)
    return [ItemResponse.model_validate(item) for item in items]


@router.post("", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
def create_item(
    data: ItemCreate,
    current_user: User = Depends(get_current_active_user),
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    """
    Create a new item.

    Requires authentication.
    """
    item = service.create_item(current_user.id, data)
    return ItemResponse.model_validate(item)


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    """
    Get a single item by ID.

    Requires authentication and authorization (user owns the item).
    """
    item = service.get_item(item_id, current_user.id)
    return ItemResponse.model_validate(item)


@router.patch("/{item_id}", response_model=ItemResponse)
def update_item(
    item_id: uuid.UUID,
    data: ItemUpdate,
    current_user: User = Depends(get_current_active_user),
    service: ItemService = Depends(get_item_service),
) -> ItemResponse:
    """
    Update an item.

    Requires authentication and authorization (user owns the item).
    """
    item = service.update_item(item_id, current_user.id, data)
    return ItemResponse.model_validate(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    service: ItemService = Depends(get_item_service),
) -> None:
    """
    Delete an item.

    Requires authentication and authorization (user owns the item).
    """
    service.delete_item(item_id, current_user.id)
