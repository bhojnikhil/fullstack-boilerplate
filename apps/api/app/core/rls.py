"""Per-transaction session variables read by the row-level security policies.

Tenant tables carry policies (see ``alembic/versions/0005_workspaces_rls.py``) that
compare rows with three settings:

- ``app.user_id``: the signed-in user, set by the authentication dependency;
- ``app.workspace_id``: the active workspace, set only after membership is proven
  (``app.modules.workspaces.dependencies``), when a workspace is created, or while an
  invitation is accepted;
- ``app.invitation_hash``: the SHA-256 of the invitation token being accepted. It is
  the only way to see an invitation without being a member of its workspace.

The values live in ``AsyncSession.info`` and are applied with ``set_config(..., true)``
(``SET LOCAL``) at the start of every transaction the session begins, so a commit in
the middle of a request cannot drop them. A transaction that never sets them sees no
tenant rows.
"""

from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, SessionTransaction

USER_ID = "app.user_id"
WORKSPACE_ID = "app.workspace_id"
INVITATION_HASH = "app.invitation_hash"
SETTINGS = (USER_ID, WORKSPACE_ID, INVITATION_HASH)
INFO_PREFIX = "rls:"

_APPLY = text("SELECT set_config(:name, :value, true)")


def _apply_pending(
    session: Session, transaction: SessionTransaction, connection: Connection
) -> None:
    """Start of every transaction: restore the values bound earlier on this session."""
    for name in SETTINGS:
        value = session.info.get(INFO_PREFIX + name)
        if value:
            connection.execute(_APPLY, {"name": name, "value": value})


# The listener is global but only acts on sessions that bound a value, so sessions for
# the rate limiter or deferred work are unaffected.
event.listen(Session, "after_begin", _apply_pending)


async def bind(db: AsyncSession, name: str, value: str | None) -> None:
    """Set (or, with ``None``, clear) one variable for this session's transactions."""
    key = INFO_PREFIX + name
    if value is None:
        db.info.pop(key, None)
    else:
        db.info[key] = value
    await db.execute(_APPLY, {"name": name, "value": value or ""})
