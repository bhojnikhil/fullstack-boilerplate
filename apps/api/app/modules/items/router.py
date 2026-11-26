"""Example item CRUD routes."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from app.core import API_PREFIX
from app.core.db import RequestSession
from app.core.errors import ErrorEnvelope
from app.core.pagination import DEFAULT_PAGE_SIZE, PageCursor, PageSize
from app.modules.auth.dependencies import Mutation
from app.modules.items.repository import ItemRepository
from app.modules.items.schemas import ItemCreate, ItemPage, ItemResponse, ItemUpdate
from app.modules.items.service import ItemService
from app.modules.workspaces.dependencies import ActiveWorkspace

router = APIRouter(
    prefix=f"{API_PREFIX}/items",
    tags=["items"],
    responses={code: {"model": ErrorEnvelope} for code in (400, 401, 403, 404)},
)
CONFLICT: dict[int | str, dict[str, Any]] = {409: {"model": ErrorEnvelope}}
NOT_FOUND: dict[int | str, dict[str, Any]] = {404: {"model": ErrorEnvelope}}


async def get_item_service(db: RequestSession, workspace: ActiveWorkspace) -> ItemService:
    """Items of the workspace named by ``X-Workspace-Id`` (404 for non-members)."""
    return ItemService(ItemRepository(db, workspace.workspace.id))


Items = Annotated[ItemService, Depends(get_item_service)]


@router.get("")
async def list_items(
    service: Items,
    limit: PageSize = DEFAULT_PAGE_SIZE,
    cursor: PageCursor = None,
) -> ItemPage:
    items, next_cursor = await service.list_items(limit, cursor)
    return ItemPage(
        items=[ItemResponse.model_validate(item) for item in items], next_cursor=next_cursor
    )


@router.post("", status_code=status.HTTP_201_CREATED, responses=CONFLICT)
async def create_item(
    data: ItemCreate, workspace: ActiveWorkspace, service: Items, mutation: Mutation
) -> ItemResponse:
    item = await service.create_item(workspace.user.id, data)
    return mutation.save(ItemResponse.model_validate(item), status.HTTP_201_CREATED)


@router.get("/{item_id}", responses=NOT_FOUND)
async def get_item(item_id: uuid.UUID, service: Items) -> ItemResponse:
    item = await service.get_item(item_id)
    return ItemResponse.model_validate(item)


@router.patch("/{item_id}", responses=NOT_FOUND | CONFLICT)
async def update_item(
    item_id: uuid.UUID,
    data: ItemUpdate,
    service: Items,
    mutation: Mutation,
) -> ItemResponse:
    item = await service.update_item(item_id, data)
    return mutation.save(ItemResponse.model_validate(item))


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT, responses=NOT_FOUND | CONFLICT)
async def delete_item(item_id: uuid.UUID, service: Items, mutation: Mutation) -> None:
    await service.delete_item(item_id)
    mutation.save(None, status.HTTP_204_NO_CONTENT)
