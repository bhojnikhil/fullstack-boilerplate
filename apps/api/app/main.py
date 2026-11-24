"""FastAPI application assembly."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.exceptions import HTTPException

from app.core import API_PREFIX, health
from app.core.config import Settings
from app.core.db import SessionFactory
from app.core.errors import (
    DomainError,
    ErrorEnvelope,
    domain_error_handler,
    http_error_handler,
    validation_error_handler,
)
from app.core.idempotency import ReplayResponseError, replay_handler
from app.core.logging import configure_logging
from app.core.middleware import (
    REQUEST_ID,
    BodyLimitMiddleware,
    CORSEnvelopeMiddleware,
    ErrorMiddleware,
    RequestContextMiddleware,
    TrustedHostEnvelopeMiddleware,
)
from app.modules.auth import router as auth
from app.modules.items import router as items


def operation_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "api"
    return f"{tag}_{route.name}"


def create_app(config: Settings, sessions: SessionFactory | None = None) -> FastAPI:
    engine = None
    if sessions is None:
        engine = create_async_engine(
            config.database(),
            pool_pre_ping=True,
            pool_timeout=5,
            hide_parameters=True,
            connect_args={"connect_timeout": 3, "prepare_threshold": None},
        )
        sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is not None:
                await engine.dispose()

    app = FastAPI(
        title="Boilerplate API",
        version="1.0.0",
        lifespan=lifespan,
        exception_handlers={
            ReplayResponseError: replay_handler,
            DomainError: domain_error_handler,
            HTTPException: http_error_handler,
            RequestValidationError: validation_error_handler,
        },
        generate_unique_id_function=operation_id,
        redirect_slashes=False,
    )
    app.state.settings = config
    app.state.session_factory = sessions
    app.state.migration_heads = health.migration_heads()

    configure_logging(config.env)
    app.add_middleware(BodyLimitMiddleware, limit=config.max_request_body_bytes)
    app.add_middleware(ErrorMiddleware)
    app.add_middleware(
        CORSEnvelopeMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", REQUEST_ID],
        expose_headers=[REQUEST_ID],
    )
    app.add_middleware(TrustedHostEnvelopeMiddleware, allowed_hosts=config.trusted_hosts)
    app.add_middleware(RequestContextMiddleware, env=config.env)

    api = APIRouter(
        responses={status: {"model": ErrorEnvelope} for status in (400, 413, 422, 500)},
    )
    api.include_router(auth.router)
    api.include_router(items.router)
    app.include_router(api)
    app.include_router(health.router)

    @app.get(API_PREFIX, tags=["api"])
    async def root() -> dict[str, str]:
        return {
            "message": "Welcome to Boilerplate API",
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    return app


app = create_app(Settings())
