from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import DomainError

SessionFactory = async_sessionmaker[AsyncSession]


def get_session_factory(request: Request) -> SessionFactory:
    factory: SessionFactory = request.app.state.session_factory
    return factory


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    # Function scope serializes the response before commit and commits before ASGI sends it.
    # Closing the session rolls back anything that was not committed.
    async with get_session_factory(request)() as session:
        try:
            yield session
        except DomainError as error:
            # Some failures must keep their side effects, e.g. a session revoked
            # because a refresh token was replayed, or a failed-login audit event.
            if error.commit:
                await session.commit()
            raise
        await session.commit()


RequestSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
