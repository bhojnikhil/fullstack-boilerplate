import base64
import binascii
import re
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Query
from pydantic import BaseModel

from app.core.errors import DomainError, ErrorCode

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25
MAX_CURSOR_LENGTH = 100
PageSize = Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)]
PageCursor = Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)]


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


type Cursor = tuple[datetime, UUID]


def encode_cursor(position: Cursor) -> str:
    created_at, identifier = position
    payload = f"1|{created_at.isoformat()}|{identifier}"
    return base64.urlsafe_b64encode(payload.encode("ascii")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> Cursor:
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
            raise ValueError
        decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode("ascii")
        version, timestamp, identifier = decoded.split("|")
        created_at = datetime.fromisoformat(timestamp)
        position = (created_at, UUID(identifier))
        if version != "1" or created_at.tzinfo is None:
            raise ValueError
    except (ValueError, binascii.Error) as err:
        raise DomainError(ErrorCode.INVALID_CURSOR) from err

    return position
