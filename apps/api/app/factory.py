"""FastAPI application assembly. ``app.main`` builds the app from the environment."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from starlette.exceptions import HTTPException

from app.core import API_PREFIX, appversion, health
from app.core.appversion import APP_VERSION_HEADER, AppVersionGate
from app.core.client import PLATFORM_HEADER
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
from app.core.observability import init_sentry
from app.core.ratelimit import RateLimiter, build_rate_limit_backend
from app.integrations.google_id_token import GoogleIdTokenVerifier
from app.integrations.pwned_passwords import BreachedPasswordChecker
from app.integrations.storage import build_storage
from app.modules.auth import router as auth
from app.modules.auth.cookies import CSRF_HEADER
from app.modules.auth.deletion import AccountDeletionHook
from app.modules.devices import router as devices
from app.modules.items import router as items
from app.modules.workspaces import router as workspaces
from app.modules.workspaces.deletion import WorkspaceDeletionHook
from app.modules.workspaces.dependencies import WORKSPACE_HEADER


def operation_id(route: APIRoute) -> str:
    tag = route.tags[0] if route.tags else "api"
    return f"{tag}_{route.name}"


def database_engine(config: Settings, **pool: int) -> AsyncEngine:
    return create_async_engine(
        config.database(),
        pool_pre_ping=True,
        pool_timeout=5,
        hide_parameters=True,
        connect_args={"connect_timeout": 3, "prepare_threshold": None},
        **pool,
    )


def create_app(
    config: Settings,
    sessions: SessionFactory | None = None,
    *,
    rate_limit_sessions: SessionFactory | None = None,
) -> FastAPI:
    engines: list[AsyncEngine] = []
    if sessions is None:
        engines.append(database_engine(config))
        sessions = async_sessionmaker(engines[-1], expire_on_commit=False)
    if config.rate_limit_backend == "postgres" and rate_limit_sessions is None:
        # Counters are written while the request holds a connection from the main pool.
        # A separate small pool means bursts of sign-ins cannot exhaust the main pool
        # waiting on themselves.
        engines.append(database_engine(config, pool_size=2, max_overflow=3))
        rate_limit_sessions = async_sessionmaker(engines[-1], expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            for engine in engines:
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
    app.state.shipped_revisions = health.shipped_revisions()
    app.state.rate_limiter = RateLimiter(
        build_rate_limit_backend(config, rate_limit_sessions or sessions), config
    )
    app.state.storage = build_storage(config)
    app.state.google_verifier = (
        GoogleIdTokenVerifier(config.google_client_ids) if config.google_auth_enabled else None
    )
    app.state.breach_checker = BreachedPasswordChecker() if config.password_breach_check else None
    # Modules that own user data register deletion hooks here (see auth/deletion.py).
    deletion_hooks: list[AccountDeletionHook] = [WorkspaceDeletionHook()]
    app.state.account_deletion_hooks = deletion_hooks

    configure_logging(config.env)
    init_sentry(config, "api")
    app.add_middleware(AppVersionGate, minimum=config.min_supported_app_version)
    app.add_middleware(BodyLimitMiddleware, limit=config.max_request_body_bytes)
    app.add_middleware(ErrorMiddleware)
    app.add_middleware(
        CORSEnvelopeMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            WORKSPACE_HEADER,
            "X-App-Version",
            REQUEST_ID,
            PLATFORM_HEADER,
            APP_VERSION_HEADER,
            CSRF_HEADER,
        ],
        expose_headers=[REQUEST_ID],
    )
    app.add_middleware(TrustedHostEnvelopeMiddleware, allowed_hosts=config.trusted_hosts)
    app.add_middleware(RequestContextMiddleware, env=config.env)

    api = APIRouter(
        responses={status: {"model": ErrorEnvelope} for status in (400, 413, 422, 500)},
    )
    api.include_router(auth.router)
    api.include_router(auth.me_router)
    api.include_router(workspaces.router)
    api.include_router(workspaces.invitations_router)
    api.include_router(items.router)
    api.include_router(devices.router)
    api.include_router(appversion.router)
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
