"""Example item CRUD routes."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.core import API_PREFIX
from app.core.db import RequestSession
from app.core.errors import ErrorEnvelope
from app.core.pagination import DEFAULT_PAGE_SIZE, Page, PageCursor, PageSize
from app.modules.auth.dependencies import CurrentUser, Mutation
from app.modules.items.repository import ItemRepository
from app.modules.items.schemas import ItemCreate, ItemResponse, ItemUpdate
from app.modules.items.service import ItemService

router = APIRouter(
    prefix=f"{API_PREFIX}/items",
    tags=["items"],
    responses={code: {"model": ErrorEnvelope} for code in (401, 403)},
)
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorEnvelope}}
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}


async def get_item_service(db: RequestSession) -> ItemService:
    return ItemService(ItemRepository(db))


Items = Annotated[ItemService, Depends(get_item_service)]


@router.get("")
async def list_items(
    current_user: CurrentUser,
    service: Items,
    limit: PageSize = DEFAULT_PAGE_SIZE,
    cursor: PageCursor = None,
) -> Page[ItemResponse]:
    items, next_cursor = await service.get_user_items(current_user.id, limit, cursor)
    return Page(
        items=[ItemResponse.model_validate(item) for item in items], next_cursor=next_cursor
    )


@router.post("", status_code=status.HTTP_201_CREATED, responses=CONFLICT)
async def create_item(
    data: ItemCreate, current_user: CurrentUser, service: Items, mutation: Mutation
) -> ItemResponse:
    item = await service.create_item(current_user.id, data)
    return mutation.save(ItemResponse.model_validate(item), status.HTTP_201_CREATED)


@router.get("/{item_id}", responses=NOT_FOUND)
async def get_item(item_id: uuid.UUID, current_user: CurrentUser, service: Items) -> ItemResponse:
    item = await service.get_item(item_id, current_user.id)
    return ItemResponse.model_validate(item)


@router.patch("/{item_id}", responses=NOT_FOUND | CONFLICT)
async def update_item(
    item_id: uuid.UUID,
    data: ItemUpdate,
    current_user: CurrentUser,
    service: Items,
    mutation: Mutation,
) -> ItemResponse:
    item = await service.update_item(item_id, current_user.id, data)
    return mutation.save(ItemResponse.model_validate(item))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND | CONFLICT)
async def delete_item(
    item_id: uuid.UUID, current_user: CurrentUser, service: Items, mutation: Mutation
) -> None:
    await service.delete_item(item_id, current_user.id)
    mutation.save(None, status.HTTP_204_NO_CONTENT)
