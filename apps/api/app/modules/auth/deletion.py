"""Extension point for account deletion.

``DELETE /v1/me`` runs every hook in ``app.state.account_deletion_hooks`` inside the
request's transaction, before the user row is deleted:

1. ``check`` for every hook. Raise ``AccountDeletionBlockedError`` to refuse; the API
   answers 409 ``account_deletion_blocked`` with the error's ``details``.
2. ``before_delete`` for every hook, to delete or anonymize data the user owns
   that foreign-key cascades do not cover.

Phase 5 (workspaces) registers a hook that blocks deletion while the user is the
sole owner of a workspace with other members, and deletes the user's solo
workspaces. Register hooks in ``app.main.create_app``.
"""

from collections.abc import Mapping
from typing import Protocol

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError, ErrorCode
from app.modules.auth.models import User


class AccountDeletionBlockedError(DomainError):
    def __init__(self, message: str, details: Mapping[str, object] | None = None) -> None:
        super().__init__(ErrorCode.ACCOUNT_DELETION_BLOCKED, message, details=details)


class AccountDeletionHook(Protocol):
    async def check(self, db: AsyncSession, user: User) -> None: ...

    async def before_delete(self, db: AsyncSession, user: User) -> None: ...


def get_account_deletion_hooks(request: Request) -> list[AccountDeletionHook]:
    hooks: list[AccountDeletionHook] = request.app.state.account_deletion_hooks
    return hooks
