"""Email/password accounts: registration, sign-in, verification, reset and sessions.

Responses never reveal whether an email is registered: registration and reset
requests answer the same way for every address, sign-in failures share one error,
and accounts without a password are checked against a dummy hash.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEventType, record_event
from app.core.client import ClientInfo
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.core.pagination import Cursor, decode_cursor, encode_cursor
from app.core.ratelimit import RateLimiter
from app.core.security import (
    hash_password,
    keyed_digest,
    new_token,
    token_digest,
    verify_password,
)
from app.integrations.email import Mailer
from app.integrations.email.templates import Template
from app.integrations.pwned_passwords import BreachedPasswordChecker
from app.modules.auth import limits
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.models import (
    AccountToken,
    AccountTokenPurpose,
    AuthSession,
    SessionRevocation,
    SignInMethod,
    User,
)
from app.modules.auth.repository import AccountTokenRepository, SessionRepository, UserRepository
from app.modules.auth.schemas import LoginRequest, RegisterRequest, ResetPasswordRequest
from app.modules.auth.sessions import IssuedTokens, SessionService

# Web pages that receive emailed tokens (built in phase 8). Tokens go in the URL
# fragment, which browsers do not send to servers or in Referer headers.
VERIFY_EMAIL_PATH = "/auth/verify-email"
RESET_PASSWORD_PATH = "/auth/reset-password"
CONFIRM_EMAIL_PATH = "/auth/confirm-email"
SIGN_IN_PATH = "/auth/login"
FORGOT_PASSWORD_PATH = "/auth/forgot-password"


def web_link(config: Settings, path: str, token: str | None = None) -> str:
    link = f"{str(config.web_url).rstrip('/')}{path}"
    return f"{link}#token={token}" if token else link


def describe(duration: timedelta) -> str:
    minutes = int(duration.total_seconds() // 60)
    if minutes % 60:
        return f"{minutes} minutes"
    hours = minutes // 60
    return "1 hour" if hours == 1 else f"{hours} hours"


class AccountEmails:
    """Issues single-use emailed tokens. Only their SHA-256 is stored."""

    def __init__(self, db: AsyncSession, config: Settings, mailer: Mailer) -> None:
        self.config = config
        self.mailer = mailer
        self.tokens = AccountTokenRepository(db)

    async def issue(
        self, user: User, purpose: AccountTokenPurpose, email: str, lifetime: timedelta
    ) -> str:
        token = new_token()
        expires_at = datetime.now(UTC) + lifetime
        await self.tokens.add(user.id, purpose, token_digest(token), email, expires_at)
        return token

    async def send_verification(self, user: User) -> None:
        lifetime = timedelta(hours=self.config.email_token_expire_hours)
        token = await self.issue(user, AccountTokenPurpose.VERIFY_EMAIL, user.email, lifetime)
        self.mailer.send(
            Template.VERIFY_EMAIL,
            user.email,
            name=user.name,
            link=web_link(self.config, VERIFY_EMAIL_PATH, token),
            expires=describe(lifetime),
        )

    async def consume(self, purpose: AccountTokenPurpose, token: str) -> AccountToken:
        record = await self.tokens.lock_valid(purpose, token_digest(token))
        if record is None:
            raise DomainError(ErrorCode.INVALID_OR_EXPIRED_TOKEN)
        # Single use: consuming one token retires every token of that kind for the user.
        await self.tokens.delete_for_user(record.user_id, purpose)
        return record


class PasswordPolicy:
    def __init__(self, checker: BreachedPasswordChecker | None) -> None:
        self.checker = checker

    async def check(self, password: str) -> None:
        # Length limits are part of the request schemas (shown in the OpenAPI schema).
        if self.checker is not None and await self.checker.is_breached(password):
            raise DomainError(ErrorCode.PASSWORD_BREACHED)


class AuthService:
    def __init__(
        self,
        db: AsyncSession,
        config: Settings,
        mailer: Mailer,
        limiter: RateLimiter,
        client: ClientInfo,
        policy: PasswordPolicy,
    ) -> None:
        self.db = db
        self.config = config
        self.mailer = mailer
        self.limiter = limiter
        self.client = client
        self.policy = policy
        self.users = UserRepository(db)
        self.sessions = SessionService(db, config)
        self.session_rows = SessionRepository(db)
        self.emails = AccountEmails(db, config, mailer)

    def audit(self, event: AuditEventType, **fields: str | int | bool | None) -> None:
        user_id = fields.pop("user_id", None)
        session_id = fields.pop("session_id", None)
        record_event(
            self.db,
            event,
            client=self.client,
            user_id=uuid.UUID(str(user_id)) if user_id else None,
            session_id=uuid.UUID(str(session_id)) if session_id else None,
            **fields,
        )

    async def register(self, data: RegisterRequest) -> None:
        await self.limiter.hit(limits.REGISTER_PER_IP, self.client.ip)
        await self.limiter.hit(limits.REGISTER_PER_ACCOUNT, data.email)
        await self.policy.check(data.password)
        # Hash before looking anything up so timing is the same for every address.
        hashed = await hash_password(data.password)
        user = await self.users.create(data.email, data.name, hashed_password=hashed)
        if user is not None:
            self.audit(AuditEventType.ACCOUNT_REGISTERED, user_id=str(user.id), method="password")
            await self.emails.send_verification(user)
            return

        existing = await self.users.get_by_email(data.email)
        if existing is None or not existing.is_active:
            return
        if existing.email_verified_at is None:
            # Never touch the existing password; only the inbox owner can verify it.
            await self.emails.send_verification(existing)
        else:
            self.mailer.send(
                Template.ACCOUNT_EXISTS,
                existing.email,
                name=existing.name,
                sign_in_link=web_link(self.config, SIGN_IN_PATH),
                reset_link=web_link(self.config, FORGOT_PASSWORD_PATH),
            )

    async def login(self, data: LoginRequest) -> tuple[IssuedTokens, User]:
        await self.limiter.hit(limits.LOGIN_PER_IP, self.client.ip)
        await self.limiter.hit(limits.LOGIN_PER_ACCOUNT, data.email)
        await self.limiter.ensure_not_locked(limits.LOGIN_FAILURES, data.email)

        user = await self.users.get_by_email(data.email)
        valid, replacement = await verify_password(
            data.password, user.hashed_password if user is not None else None
        )
        if user is None or not valid:
            await self.limiter.record_failure(limits.LOGIN_FAILURES, data.email)
            self.audit(
                AuditEventType.LOGIN_FAILED,
                user_id=str(user.id) if user is not None else None,
                method="password",
                email_hash=keyed_digest(self.config, "email", data.email),
            )
            raise DomainError(ErrorCode.INVALID_CREDENTIALS, commit=True)
        await self.limiter.clear_failures(limits.LOGIN_FAILURES, data.email)
        if not user.is_active:
            self.audit(AuditEventType.LOGIN_FAILED, user_id=str(user.id), reason="inactive")
            raise DomainError(ErrorCode.INACTIVE_USER, commit=True)

        if replacement is not None:
            # bcrypt (pre-v2) or outdated argon2 parameters: upgrade transparently.
            user.hashed_password = replacement
        issued = await self.sessions.start(
            user, SignInMethod.PASSWORD, self.client, data.device_name
        )
        self.audit(
            AuditEventType.LOGIN_SUCCEEDED,
            user_id=str(user.id),
            session_id=str(issued.session.id),
            method="password",
            rehashed=replacement is not None,
        )
        return issued, user

    async def logout(self, context: AuthContext) -> None:
        self.sessions.revoke(context.session, SessionRevocation.LOGOUT)
        self.audit(
            AuditEventType.LOGOUT, user_id=str(context.user.id), session_id=str(context.session.id)
        )

    async def verify_email(self, token: str) -> None:
        record = await self.emails.consume(AccountTokenPurpose.VERIFY_EMAIL, token)
        user = await self.users.get_by_id(record.user_id)
        # A link sent to a previous address must not verify the current one.
        if user is None or user.email.lower() != record.email.lower():
            raise DomainError(ErrorCode.INVALID_OR_EXPIRED_TOKEN)
        if user.email_verified_at is None:
            user.email_verified_at = datetime.now(UTC)
            self.audit(AuditEventType.EMAIL_VERIFIED, user_id=str(user.id))

    async def resend_verification(self, user: User) -> None:
        await self.limiter.hit(limits.VERIFICATION_PER_IP, self.client.ip)
        await self.limiter.hit(limits.VERIFICATION_PER_ACCOUNT, str(user.id))
        if user.email_verified_at is None:
            await self.emails.send_verification(user)

    async def request_password_reset(self, email: str) -> None:
        await self.limiter.hit(limits.PASSWORD_RESET_PER_IP, self.client.ip)
        await self.limiter.hit(limits.PASSWORD_RESET_PER_ACCOUNT, email)
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            return
        lifetime = timedelta(minutes=self.config.password_reset_expire_minutes)
        token = await self.emails.issue(
            user, AccountTokenPurpose.RESET_PASSWORD, user.email, lifetime
        )
        self.mailer.send(
            Template.RESET_PASSWORD,
            user.email,
            name=user.name,
            link=web_link(self.config, RESET_PASSWORD_PATH, token),
            expires=describe(lifetime),
        )
        self.audit(AuditEventType.PASSWORD_RESET_REQUESTED, user_id=str(user.id))

    async def reset_password(self, data: ResetPasswordRequest) -> None:
        record = await self.emails.consume(AccountTokenPurpose.RESET_PASSWORD, data.token)
        user = await self.users.get_by_id(record.user_id)
        if user is None or not user.is_active or user.email.lower() != record.email.lower():
            raise DomainError(ErrorCode.INVALID_OR_EXPIRED_TOKEN)
        await self.policy.check(data.new_password)

        user.hashed_password = await hash_password(data.new_password)
        # Using the emailed link proves control of the address.
        user.email_verified_at = user.email_verified_at or datetime.now(UTC)
        revoked = await self.session_rows.revoke_all(user.id, SessionRevocation.PASSWORD_RESET)
        await self.limiter.clear_failures(limits.LOGIN_FAILURES, user.email.lower())
        self.audit(AuditEventType.PASSWORD_RESET, user_id=str(user.id), sessions_revoked=revoked)
        self.mailer.send(
            Template.PASSWORD_CHANGED,
            user.email,
            name=user.name,
            link=web_link(self.config, FORGOT_PASSWORD_PATH),
        )

    async def reauthenticate_with_password(self, context: AuthContext, password: str) -> None:
        user = context.user
        await check_current_password(self, user, password, purpose="reauthenticate")
        context.session.authenticated_at = datetime.now(UTC)
        self.audit(
            AuditEventType.REAUTHENTICATED,
            user_id=str(user.id),
            session_id=str(context.session.id),
            method="password",
        )

    async def list_sessions(
        self, context: AuthContext, limit: int, cursor: str | None
    ) -> tuple[list[AuthSession], str | None]:
        before: Cursor | None = decode_cursor(cursor) if cursor is not None else None
        rows = await self.session_rows.list_active(context.user.id, limit + 1, before)
        if len(rows) <= limit:
            return rows, None
        last = rows[limit - 1]
        return rows[:limit], encode_cursor((last.created_at, last.id))

    async def revoke_session(self, context: AuthContext, session_id: uuid.UUID) -> bool:
        """Revoke one of the user's sessions. Returns True if it was the current one."""
        if session_id == context.session.id:
            target = context.session
        else:
            found = await self.session_rows.get_active_for_user(session_id, context.user.id)
            if found is None:
                raise DomainError(ErrorCode.SESSION_NOT_FOUND)
            target = found
        self.sessions.revoke(target, SessionRevocation.USER_REVOKED)
        self.audit(
            AuditEventType.SESSION_REVOKED,
            user_id=str(context.user.id),
            session_id=str(context.session.id),
            revoked_session_id=str(session_id),
        )
        return target is context.session

    async def revoke_other_sessions(self, context: AuthContext) -> int:
        revoked = await self.session_rows.revoke_all(
            context.user.id, SessionRevocation.REVOKED_OTHERS, keep=context.session.id
        )
        self.audit(
            AuditEventType.OTHER_SESSIONS_REVOKED,
            user_id=str(context.user.id),
            session_id=str(context.session.id),
            sessions_revoked=revoked,
        )
        return revoked


async def check_current_password(
    service: AuthService, user: User, password: str, *, purpose: str
) -> None:
    """Verify a signed-in user's password with per-user backoff on failures."""
    identifier = str(user.id)
    await service.limiter.hit(limits.REAUTH_PER_ACCOUNT, identifier)
    await service.limiter.ensure_not_locked(limits.PASSWORD_CHECK_FAILURES, identifier)
    valid, replacement = await verify_password(password, user.hashed_password)
    if not valid:
        await service.limiter.record_failure(limits.PASSWORD_CHECK_FAILURES, identifier)
        service.audit(
            AuditEventType.REAUTHENTICATION_FAILED,
            user_id=identifier,
            method="password",
            purpose=purpose,
        )
        raise DomainError(ErrorCode.REAUTHENTICATION_FAILED, commit=True)
    await service.limiter.clear_failures(limits.PASSWORD_CHECK_FAILURES, identifier)
    if replacement is not None:
        user.hashed_password = replacement
