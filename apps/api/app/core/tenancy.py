"""Base for repositories of tenant data.

A tenant repository cannot be built without a workspace id and every query it runs is
filtered by it, so there is no "all workspaces" helper to call by mistake. Row-level
security (``app.core.rls``) repeats the same rule inside the database.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession


class TenantRepository:
    def __init__(self, db: AsyncSession, workspace_id: uuid.UUID) -> None:
        if not isinstance(workspace_id, uuid.UUID):
            raise TypeError("A tenant repository needs the workspace id (uuid.UUID)")
        self._db = db
        self.workspace_id = workspace_id
