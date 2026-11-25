"""Authentication (/v1/auth) and account (/v1/me) routes.

Token transport depends on the client. Requests with ``X-Platform: web`` get the
refresh token in an httpOnly cookie (and a CSRF token in the body); other clients
get the refresh token in the body and send it back in the refresh request body.
"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response, status

from app.core import API_PREFIX
from app.core.client import Client
from app.core.config import Settings, get_settings
from app.core.db import RequestSession
from app.core.errors import DomainError, ErrorCode, ErrorEnvelope
from app.core.pagination import DEFAULT_PAGE_SIZE, PageCursor, PageSize
from app.core.ratelimit import RateLimiter, get_rate_limiter
from app.integrations.email import Mail
from app.modules.auth.account import AccountService
from app.modules.auth.cookies import (
    REFRESH_COOKIE,
    clear_session_cookies,
    cleared_cookie_headers,
    require_trusted_origin,
    set_session_cookies,
    verify_csrf,
)
from app.modules.auth.deferred import DeferredWork
from app.modules.auth.deletion import AccountDeletionHook, get_account_deletion_hooks
from app.modules.auth.dependencies import Auth, Mutation
from app.modules.auth.google import GoogleService
from app.modules.auth.models import User
from app.modules.auth.schemas import (
    AcceptedResponse,
    ChangeEmailRequest,
    ChangePasswordRequest,
    EmailRequest,
    GoogleLinkRequest,
    GoogleSignInRequest,
    LoginRequest,
    ReauthenticateRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    RevokedSessionsResponse,
    SessionPage,
    SessionResponse,
    TokenRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.modules.auth.service import AuthService, PasswordPolicy
from app.modules.auth.sessions import IssuedTokens

router = APIRouter(prefix=f"{API_PREFIX}/auth", tags=["auth"])
me_router = APIRouter(prefix=f"{API_PREFIX}/me", tags=["me"])
Config = Annotated[Settings, Depends(get_settings)]
Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]
DeletionHooks = Annotated[list[AccountDeletionHook], Depends(get_account_deletion_hooks)]


def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
    return {code: {"model": ErrorEnvelope} for code in codes}


async def get_auth_service(
    request: Request,
    db: RequestSession,
    config: Config,
    mailer: Mail,
    limiter: Limiter,
    client: Client,
    deferred: DeferredWork,
) -> AuthService:
    policy = PasswordPolicy(request.app.state.breach_checker)
    return AuthService(db, config, mailer, limiter, client, policy, deferred)


Authentication = Annotated[AuthService, Depends(get_auth_service)]


async def get_google_service(
    request: Request, auth: Authentication, db: RequestSession, config: Config
) -> GoogleService:
    return GoogleService(auth, db, config, request.app.state.google_verifier)


async def get_account_service(auth: Authentication) -> AccountService:
    return AccountService(auth)


Google = Annotated[GoogleService, Depends(get_google_service)]
Accounts = Annotated[AccountService, Depends(get_account_service)]


async def token_response(
    request: Request,
    response: Response,
    issued: IssuedTokens,
    user: User,
    accounts: AccountService,
    *,
    web: bool,
) -> TokenResponse:
    request.state.user_id = str(user.id)
    response.headers["Cache-Control"] = "no-store"  # RFC 6749 section 5.1.
    profile = await accounts.describe_user(user)
    if web:
        set_session_cookies(
            response,
            accounts.config,
            issued.refresh_token,
            issued.csrf_token,
            issued.refresh_max_age,
        )
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        refresh_token=None if web else issued.refresh_token,
        csrf_token=issued.csrf_token if web else None,
        user=profile,
    )


ACCEPTED_MESSAGE = "If the address can be used, we sent an email to it. Follow it to continue."


@router.post("/register", status_code=status.HTTP_202_ACCEPTED, responses=errors(422, 429))
async def register(data: RegisterRequest, service: Authentication) -> AcceptedResponse:
    """Start registration: email a link that activates the chosen password.

    The response is the same whether or not the email is registered (existing owners
    get a notice instead), and the account work happens after the response. The
    account can sign in once the link is opened with the same password.
    """
    await service.register(data)
    return AcceptedResponse(message=ACCEPTED_MESSAGE)


@router.post("/login", responses=errors(401, 403, 429))
async def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    service: Authentication,
    accounts: Accounts,
) -> TokenResponse:
    if service.client.is_web:
        require_trusted_origin(service.client, service.config)  # Login CSRF.
    issued, user = await service.login(data)
    return await token_response(
        request, response, issued, user, accounts, web=service.client.is_web
    )


@router.post("/google", responses=errors(401, 403, 404, 409, 429, 503))
async def google_sign_in(
    request: Request,
    response: Response,
    data: GoogleSignInRequest,
    service: Authentication,
    google: Google,
    accounts: Accounts,
) -> TokenResponse:
    """Sign in or sign up with a Google ID token (Google Identity Services or native)."""
    if service.client.is_web:
        require_trusted_origin(service.client, service.config)
    issued, user = await google.sign_in(data)
    return await token_response(
        request, response, issued, user, accounts, web=service.client.is_web
    )


@router.post("/refresh", responses=errors(401, 403))
async def refresh(
    request: Request,
    response: Response,
    service: Authentication,
    accounts: Accounts,
    data: RefreshRequest | None = None,
) -> TokenResponse:
    """Rotate the refresh token: from the body (mobile) or the cookie (web, CSRF-checked)."""
    config = service.config
    if data is not None:
        issued, user = await service.sessions.rotate(data.refresh_token, service.client)
        return await token_response(request, response, issued, user, accounts, web=False)

    require_trusted_origin(service.client, config)
    cookie = request.cookies.get(REFRESH_COOKIE)
    if not cookie:
        raise DomainError(ErrorCode.INVALID_REFRESH_TOKEN)
    try:
        issued, user = await service.sessions.rotate(
            cookie, service.client, verify=lambda session: verify_csrf(request, config, session.id)
        )
    except DomainError as error:
        if error.code != ErrorCode.CSRF_FAILED:
            error.headers.extend(cleared_cookie_headers(config))
        raise
    return await token_response(request, response, issued, user, accounts, web=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, responses=errors(401, 403))
async def logout(context: Auth, service: Authentication) -> None:
    """Revoke the current session (its access and refresh tokens stop working)."""
    # Refresh cookies are scoped to /refresh and may belong to another tab's
    # session. Revocation invalidates this session without clearing that cookie.
    await service.logout(context)


@router.post(
    "/verify-email", status_code=status.HTTP_204_NO_CONTENT, responses=errors(400, 401, 429)
)
async def verify_email(data: VerifyEmailRequest, service: Authentication) -> None:
    """Confirm the address with the emailed token and the password chosen at registration."""
    await service.verify_email(data)


@router.post("/verify-email/resend", status_code=status.HTTP_202_ACCEPTED, responses=errors(429))
async def resend_verification(data: EmailRequest, service: Authentication) -> AcceptedResponse:
    """Email a new verification link. The response does not reveal whether one was sent."""
    await service.resend_verification(data.email)
    return AcceptedResponse(message=ACCEPTED_MESSAGE)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED, responses=errors(429))
async def request_password_reset(data: EmailRequest, service: Authentication) -> AcceptedResponse:
    """Email a single-use reset link. The response does not reveal whether the account exists."""
    await service.request_password_reset(data.email)
    return AcceptedResponse(message=ACCEPTED_MESSAGE)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT, responses=errors(400))
async def reset_password(data: ResetPasswordRequest, service: Authentication) -> None:
    """Set a new password with an emailed token. Signs out every session."""
    await service.reset_password(data)


@router.post("/email/confirm", status_code=status.HTTP_204_NO_CONTENT, responses=errors(400, 409))
async def confirm_email_change(data: TokenRequest, accounts: Accounts) -> None:
    await accounts.confirm_email_change(data.token)


@router.post(
    "/reauthenticate",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=errors(401, 403, 404, 429, 503),
)
async def reauthenticate(
    data: ReauthenticateRequest, context: Auth, service: Authentication, google: Google
) -> None:
    """Confirm the user's identity on this session before a sensitive change."""
    if data.password is not None:
        await service.reauthenticate_with_password(context, data.password)
    else:
        assert data.id_token is not None  # Guaranteed by the schema.
        await google.reauthenticate(context, data.id_token)


@router.post(
    "/google/link",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=errors(401, 403, 404, 409, 503),
)
async def link_google(data: GoogleLinkRequest, context: Auth, google: Google) -> None:
    await google.link_to_current_user(context, data.id_token)


@router.delete(
    "/google/link", status_code=status.HTTP_204_NO_CONTENT, responses=errors(401, 403, 404, 409)
)
async def unlink_google(response: Response, context: Auth, google: Google, config: Config) -> None:
    """Unlink Google; sessions started with Google (possibly this one) are signed out."""
    if await google.unlink(context):
        clear_session_cookies(response, config)


@router.get("/sessions", responses=errors(401, 403))
async def list_sessions(
    context: Auth,
    service: Authentication,
    limit: PageSize = DEFAULT_PAGE_SIZE,
    cursor: PageCursor = None,
) -> SessionPage:
    sessions, next_cursor = await service.list_sessions(context, limit, cursor)
    return SessionPage(
        items=[SessionResponse.build(session, context.session.id) for session in sessions],
        next_cursor=next_cursor,
    )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=errors(401, 403, 404),
)
async def revoke_session(
    session_id: uuid.UUID, response: Response, context: Auth, service: Authentication
) -> None:
    if await service.revoke_session(context, session_id):
        clear_session_cookies(response, service.config)


@router.post("/sessions/revoke-others", responses=errors(401, 403))
async def revoke_other_sessions(context: Auth, service: Authentication) -> RevokedSessionsResponse:
    return RevokedSessionsResponse(revoked=await service.revoke_other_sessions(context))


@me_router.get("", responses=errors(401, 403))
async def get_profile(context: Auth, accounts: Accounts) -> UserResponse:
    return await accounts.describe_user(context.user)


@me_router.patch("", responses=errors(401, 403, 409))
async def update_profile(
    data: UpdateProfileRequest, context: Auth, accounts: Accounts, mutation: Mutation
) -> UserResponse:
    user = await accounts.update_profile(context.user, data)
    return mutation.save(await accounts.describe_user(user))


@me_router.delete("", status_code=status.HTTP_204_NO_CONTENT, responses=errors(401, 403, 409))
async def delete_account(
    response: Response, context: Auth, accounts: Accounts, hooks: DeletionHooks
) -> None:
    """Delete the account. Requires a sign-in or re-authentication in the last few minutes."""
    await accounts.delete_account(context, hooks)
    clear_session_cookies(response, accounts.config)


@me_router.post(
    "/password", status_code=status.HTTP_204_NO_CONTENT, responses=errors(401, 403, 409, 429)
)
async def change_password(data: ChangePasswordRequest, context: Auth, accounts: Accounts) -> None:
    """Change the password (current one required). Other sessions are signed out."""
    await accounts.change_password(context, data)


@me_router.post("/email", status_code=status.HTTP_202_ACCEPTED, responses=errors(401, 403, 429))
async def request_email_change(
    data: ChangeEmailRequest, context: Auth, accounts: Accounts
) -> AcceptedResponse:
    """Send a confirmation link to the new address. Requires recent authentication."""
    await accounts.request_email_change(context, data.new_email)
    return AcceptedResponse(message=ACCEPTED_MESSAGE)
