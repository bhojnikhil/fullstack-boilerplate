"""Email/password accounts: registration, sign-in, verification, reset and sessions.

Account ownership rules (see docs/adr/0010-rate-limits-email-audit.md):

- Registration never gives an account a usable password. The chosen password waits
  in the emailed verification token; opening the link and entering that password
  activates it. A link from someone else's registration is useless without their
  password. Several independently bound links can be pending at once.
- Only accounts with a verified email can sign in with a password.
- When someone proves control of an unverified account's inbox (verification or
  password reset), they take it over: other sessions and emailed tokens are removed.
  A reset preserves an already-linked identity only for a passwordless account.

Responses never reveal whether an email is registered: registration, verification
resends and reset requests answer before looking anything up (the account work runs
after the response), and sign-in failures share one error and the same hashing work.
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
from app.integrations.email import MailSender
from app.integrations.email.templates import Template
from app.integrations.pwned_passwords import BreachedPasswordChecker
from app.modules.auth import limits
from app.modules.auth.deferred import Deferred
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.models import (
    AccountToken,
    AccountTokenPurpose,
    AuthSession,
    OAuthLinkState,
    SessionRevocation,
    SignInMethod,
    User,
)
from app.modules.auth.repository import (
    AccountTokenRepository,
    OAuthAccountRepository,
    SessionRepository,
    UserRepository,
    lock_email,
)
from app.modules.auth.schemas import (
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.modules.auth.sessions import IssuedTokens, SessionService

# Web pages that receive emailed tokens. Tokens go in the URL fragment, which
# browsers do not send to servers or in Referer headers.
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


async def issue_token(
    db: AsyncSession,
    user: User,
    purpose: AccountTokenPurpose,
    email: str,
    lifetime: timedelta,
    *,
    password_hash: str | None = None,
    pending_name: str | None = None,
) -> str:
    """Create a single-use emailed token. Only its SHA-256 is stored."""
    token = new_token()
    await AccountTokenRepository(db).add(
        user.id,
        purpose,
        token_digest(token),
        email,
        datetime.now(UTC) + lifetime,
        password_hash=password_hash,
        pending_name=pending_name,
    )
    return token


async def send_verification(
    db: AsyncSession,
    mail: MailSender,
    config: Settings,
    user: User,
    password_hash: str,
    pending_name: str | None = None,
) -> None:
    """Retain a bounded set of independently bound verification links."""
    await AccountTokenRepository(db).trim_verifications(user.id, keep=4)
    lifetime = timedelta(hours=config.email_token_expire_hours)
    token = await issue_token(
        db,
        user,
        AccountTokenPurpose.VERIFY_EMAIL,
        user.email,
        lifetime,
        password_hash=password_hash,
        pending_name=pending_name,
    )
    mail.send(
        Template.VERIFY_EMAIL,
        user.email,
        name=pending_name or user.name,
        link=web_link(config, VERIFY_EMAIL_PATH, token),
        expires=describe(lifetime),
    )


async def register_account(
    db: AsyncSession,
    mail: MailSender,
    config: Settings,
    client: ClientInfo,
    email: str,
    name: str,
    password_hash: str,
) -> None:
    """Deferred part of registration (runs after the response)."""
    users = UserRepository(db)
    await lock_email(db, email)
    user = await users.get_by_email(email)
    if user is None:
        user = await users.create(email, "User")
        if user is None:  # pragma: no cover - the email lock prevents this
            return
        record_event(
            db, AuditEventType.ACCOUNT_REGISTERED, client=client, user_id=user.id, method="password"
        )
        await send_verification(db, mail, config, user, password_hash, name)
        return
    user = await users.lock(user.id)
    if user is None or not user.is_active:
        return
    if user.email_verified_at is None:
        await send_verification(db, mail, config, user, password_hash, name)
    else:
        mail.send(
            Template.ACCOUNT_EXISTS,
            user.email,
            name=user.name,
            sign_in_link=web_link(config, SIGN_IN_PATH),
            reset_link=web_link(config, FORGOT_PASSWORD_PATH),
        )


async def resend_verification(
    db: AsyncSession, mail: MailSender, config: Settings, email: str
) -> None:
    """Deferred: a new link for the pending password (or, for accounts from before
    email verification existed, the current one). Either way only someone who knows
    that password can use it."""
    users, tokens = UserRepository(db), AccountTokenRepository(db)
    user = await users.get_by_email(email)
    if user is None:
        return
    user = await users.lock(user.id)
    if user is None or not user.is_active or user.email_verified_at is not None:
        return
    latest = await tokens.latest(user.id, AccountTokenPurpose.VERIFY_EMAIL)
    password_hash = latest.password_hash if latest is not None else None
    password_hash = password_hash or user.hashed_password
    if password_hash is not None:
        await send_verification(
            db, mail, config, user, password_hash, latest.pending_name if latest else None
        )


async def send_password_reset(
    db: AsyncSession, mail: MailSender, config: Settings, client: ClientInfo, email: str
) -> None:
    """Deferred part of a password reset request."""
    users = UserRepository(db)
    user = await users.get_by_email(email)
    if user is None:
        return
    user = await users.lock(user.id)
    if user is None or not user.is_active:
        return
    lifetime = timedelta(minutes=config.password_reset_expire_minutes)
    token = await issue_token(db, user, AccountTokenPurpose.RESET_PASSWORD, user.email, lifetime)
    mail.send(
        Template.RESET_PASSWORD,
        user.email,
        name=user.name,
        link=web_link(config, RESET_PASSWORD_PATH, token),
        expires=describe(lifetime),
    )
    record_event(db, AuditEventType.PASSWORD_RESET_REQUESTED, client=client, user_id=user.id)


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
        mailer: MailSender,
        limiter: RateLimiter,
        client: ClientInfo,
        policy: PasswordPolicy,
        deferred: Deferred,
    ) -> None:
        self.db = db
        self.config = config
        self.mailer = mailer
        self.limiter = limiter
        self.client = client
        self.policy = policy
        self.deferred = deferred
        self.users = UserRepository(db)
        self.tokens = AccountTokenRepository(db)
        self.identities = OAuthAccountRepository(db)
        self.sessions = SessionService(db, config)
        self.session_rows = SessionRepository(db)

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

    async def claim(
        self, user: User, *, password_hash: str | None, preserve_linked: bool = False
    ) -> int:
        """The inbox owner takes over an unverified account (call with the user locked).

        Anything set up before the inbox was proven may belong to someone else, so
        sessions, linked identities and emailed tokens go, and ``password_hash``
        (the owner's password, or None) replaces any earlier password.
        """
        user.hashed_password = password_hash
        user.email_verified_at = datetime.now(UTC)
        revoked = await self.session_rows.revoke_all(user.id, SessionRevocation.ACCOUNT_CLAIMED)
        if preserve_linked:
            identities = await self.identities.delete_for_user(
                user.id, state=OAuthLinkState.UNCONFIRMED
            )
            identities += await self.identities.delete_for_user(
                user.id, state=OAuthLinkState.UNLINKED
            )
        else:
            identities = await self.identities.delete_for_user(user.id)
        await self.tokens.delete_for_user(user.id)
        self.audit(
            AuditEventType.ACCOUNT_CLAIMED,
            user_id=str(user.id),
            sessions_revoked=len(revoked),
            identities_removed=identities,
        )
        return len(revoked)

    async def lock_token(
        self, purpose: AccountTokenPurpose, token: str
    ) -> tuple[User, AccountToken]:
        """Find a valid token, then lock its user and the token in that order.

        Verification and reset links must still match the account's address; email
        change links carry the new address instead (all tokens go when it changes).
        """
        digest = token_digest(token)
        found = await self.tokens.find_valid(purpose, digest)
        user = await self.users.lock(found.user_id) if found is not None else None
        record = await self.tokens.lock_valid(purpose, digest) if user is not None else None
        # A link sent to a previous address must not act on the current one.
        sent_elsewhere = (
            record is not None
            and purpose != AccountTokenPurpose.CHANGE_EMAIL
            and user is not None
            and user.email.lower() != record.email.lower()
        )
        if user is None or record is None or not user.is_active or sent_elsewhere:
            raise DomainError(ErrorCode.INVALID_OR_EXPIRED_TOKEN)
        return user, record

    async def register(self, data: RegisterRequest) -> None:
        await self.limiter.hit(limits.REGISTER_PER_IP, self.client.ip)
        await self.limiter.hit(limits.REGISTER_PER_ACCOUNT, data.email)
        await self.policy.check(data.password)
        password_hash = await hash_password(data.password)
        config, client = self.config, self.client

        async def work(db: AsyncSession, mail: MailSender) -> None:
            await register_account(db, mail, config, client, data.email, data.name, password_hash)

        self.deferred.run("register", work)

    async def resend_verification(self, email: str) -> None:
        await self.limiter.hit(limits.VERIFICATION_PER_IP, self.client.ip)
        await self.limiter.hit(limits.VERIFICATION_PER_ACCOUNT, email)
        config = self.config

        async def work(db: AsyncSession, mail: MailSender) -> None:
            await resend_verification(db, mail, config, email)

        self.deferred.run("resend_verification", work)

    async def verify_email(self, data: VerifyEmailRequest) -> None:
        user, record = await self.lock_token(AccountTokenPurpose.VERIFY_EMAIL, data.token)
        if user.email_verified_at is not None or record.password_hash is None:
            raise DomainError(ErrorCode.INVALID_OR_EXPIRED_TOKEN)
        identifier = user.email.lower()
        await self.limiter.ensure_not_locked(limits.LOGIN_FAILURES, identifier)
        valid, replacement = await verify_password(data.password, record.password_hash)
        if not valid:
            await self.limiter.record_failure(limits.LOGIN_FAILURES, identifier)
            self.audit(AuditEventType.LOGIN_FAILED, user_id=str(user.id), reason="verification")
            raise DomainError(ErrorCode.INVALID_CREDENTIALS, "Incorrect password", commit=True)
        await self.limiter.clear_failures(limits.LOGIN_FAILURES, identifier)
        if record.pending_name is not None:
            user.name = record.pending_name
        await self.claim(user, password_hash=replacement or record.password_hash)
        self.audit(AuditEventType.EMAIL_VERIFIED, user_id=str(user.id))

    async def login(self, data: LoginRequest) -> tuple[IssuedTokens, User]:
        await self.limiter.hit(limits.LOGIN_PER_IP, self.client.ip)
        await self.limiter.hit(limits.LOGIN_PER_ACCOUNT, data.email)
        await self.limiter.ensure_not_locked(limits.LOGIN_FAILURES, data.email)

        found = await self.users.get_by_email(data.email)
        # Only a verified account has a usable password (see the module docstring).
        checked = found.hashed_password if found and found.email_verified_at else None
        valid, replacement = await verify_password(data.password, checked)
        user = None
        if found is not None and valid:
            # Serialize with resets and password changes, then make sure the password we
            # checked is still the account's: a reset may have committed meanwhile.
            locked = await self.users.lock(found.id)
            if locked and locked.email_verified_at and locked.hashed_password == checked:
                user = locked
        if user is None:
            await self.limiter.record_failure(limits.LOGIN_FAILURES, data.email)
            self.audit(
                AuditEventType.LOGIN_FAILED,
                user_id=str(found.id) if found is not None else None,
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

    async def request_password_reset(self, email: str) -> None:
        await self.limiter.hit(limits.PASSWORD_RESET_PER_IP, self.client.ip)
        await self.limiter.hit(limits.PASSWORD_RESET_PER_ACCOUNT, email)
        config, client = self.config, self.client

        async def work(db: AsyncSession, mail: MailSender) -> None:
            await send_password_reset(db, mail, config, client, email)

        self.deferred.run("password_reset", work)

    async def reset_password(self, data: ResetPasswordRequest) -> None:
        await self.policy.check(data.new_password)
        password_hash = await hash_password(data.new_password)
        user, _ = await self.lock_token(AccountTokenPurpose.RESET_PASSWORD, data.token)
        if user.email_verified_at is None:
            # The emailed link proves control of the inbox.
            sessions_revoked = await self.claim(
                user, password_hash=password_hash, preserve_linked=user.hashed_password is None
            )
        else:
            had_password = user.hashed_password is not None
            user.hashed_password = password_hash
            sessions_revoked = len(
                await self.session_rows.revoke_all(user.id, SessionRevocation.PASSWORD_RESET)
            )
            # Pending email changes may have been started by whoever had a session.
            await self.tokens.delete_for_user(
                user.id,
                AccountTokenPurpose.RESET_PASSWORD,
                AccountTokenPurpose.CHANGE_EMAIL,
                AccountTokenPurpose.VERIFY_EMAIL,
            )
            if had_password:
                await self.identities.delete_for_user(user.id)
            else:
                await self.identities.delete_for_user(user.id, state=OAuthLinkState.UNCONFIRMED)
        await self.limiter.clear_failures(limits.LOGIN_FAILURES, user.email.lower())
        self.audit(
            AuditEventType.PASSWORD_RESET, user_id=str(user.id), sessions_revoked=sessions_revoked
        )
        self.mailer.send(
            Template.PASSWORD_CHANGED,
            user.email,
            name=user.name,
            link=web_link(self.config, FORGOT_PASSWORD_PATH),
        )

    async def reauthenticate_with_password(self, context: AuthContext, password: str) -> None:
        user = await self.users.lock(context.user.id)
        if user is None:  # pragma: no cover - the session's user row exists
            raise DomainError(ErrorCode.INVALID_TOKEN)
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
        user = await self.users.lock(context.user.id)
        if user is None:
            raise DomainError(ErrorCode.INVALID_TOKEN)
        await self.tokens.delete_for_user(user.id)
        revoked = len(
            await self.session_rows.revoke_all(
                context.user.id, SessionRevocation.REVOKED_OTHERS, keep=context.session.id
            )
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
    """Verify a signed-in user's password with per-user backoff on failures.

    Call with the user row locked so a concurrent reset cannot interleave.
    """
    identifier = str(user.id)
    await service.limiter.hit(limits.REAUTH_PER_IP, service.client.ip)
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
