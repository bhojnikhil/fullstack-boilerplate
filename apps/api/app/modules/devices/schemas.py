import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.integrations.push import EXPO_TOKEN_PATTERN

TOKEN_REGEX = EXPO_TOKEN_PATTERN.pattern


class DeviceRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expo_push_token: str = Field(pattern=TOKEN_REGEX, max_length=255)
    platform: Literal["ios", "android"]
    app_version: str = Field(min_length=1, max_length=32, pattern=r"^[0-9A-Za-z.+-]+$")


class DeviceUnregister(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expo_push_token: str = Field(pattern=TOKEN_REGEX, max_length=255)


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    platform: str
    app_version: str
    last_seen_at: datetime
