import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import Page


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class ItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    created_by_id: uuid.UUID | None
    title: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ItemPage(Page[ItemResponse]):
    pass
