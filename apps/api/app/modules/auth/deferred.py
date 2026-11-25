"""Account work that must not shape the response.

Registration, verification resends and password-reset requests answer before
looking anything up, so neither the response nor its timing reveals whether an
account exists. The work runs after the response in its own transaction, and its
emails go out after that commits. A later phase replaces this with the durable
job queue (retries, survives restarts).
"""

from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import BackgroundTasks, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.db import SessionFactory
from app.integrations.email import CollectedMail, EmailBackend, deliver

log = structlog.get_logger()
Work = Callable[[AsyncSession, CollectedMail], Awaitable[None]]


class Deferred:
    def __init__(
        self,
        tasks: BackgroundTasks,
        sessions: SessionFactory,
        backend: EmailBackend,
        config: Settings,
    ) -> None:
        self.tasks = tasks
        self.sessions = sessions
        self.backend = backend
        self.config = config

    def run(self, name: str, work: Work) -> None:
        self.tasks.add_task(self.execute, name, work)

    async def execute(self, name: str, work: Work) -> None:
        mail = CollectedMail(self.config)
        try:
            async with self.sessions.begin() as db:
                await work(db, mail)
        except Exception:
            log.exception("deferred_work_failed", work=name)
            return
        for email in mail.emails:
            await deliver(self.backend, email)


def get_deferred(
    request: Request,
    tasks: BackgroundTasks,
    config: Annotated[Settings, Depends(get_settings)],
) -> Deferred:
    return Deferred(
        tasks, request.app.state.session_factory, request.app.state.email_backend, config
    )


DeferredWork = Annotated[Deferred, Depends(get_deferred)]
