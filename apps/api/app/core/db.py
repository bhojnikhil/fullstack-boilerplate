from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

SessionFactory = async_sessionmaker[AsyncSession]


def get_session_factory(request: Request) -> SessionFactory:
    factory: SessionFactory = request.app.state.session_factory
    return factory


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    # Function scope serializes the response before commit and commits before ASGI sends it.
    async with get_session_factory(request).begin() as session:
        yield session


RequestSession = Annotated[AsyncSession, Depends(get_db, scope="function")]
