"""Sign in with Google (ID tokens), plus explicit linking and unlinking.

Rules (pre-account-takeover defense, docs/adr/0009-google-id-token-sign-in.md):

- A Google identity with a usable link (state ``linked``) signs in to its account.
- Anything else needs Google to vouch for the address *today*: a Gmail address, or a
  Workspace account whose email is in its hosted domain ("authoritative"). Other
  addresses were verified once, which does not prove current ownership, so they can
  only sign in through a link made from a signed-in, verified account.
- With an authoritative address: no account creates one; a verified account is
  linked automatically; an unverified account is claimed (everything set up before
  the inbox was proven is removed) and then linked. An identity the user unlinked is
  never relinked automatically.
- Explicit linking needs a verified email and recent re-authentication. Unlinking
  signs out the sessions started with Google.

Other providers (e.g. Sign in with Apple) would follow the same shape: a verifier
in ``app.integrations`` and a service like this one keyed by ``OAuthProvider``.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEventType
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.integrations.email.templates import Template
from app.integrations.google_id_token import (
    GoogleIdentity,
    GoogleIdTokenVerifier,
    GoogleTokenError,
    GoogleUnavailableError,
)
from app.modules.auth import limits
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.models import (
    OAuthAccount,
    OAuthLinkState,
    OAuthProvider,
    SessionRevocation,
    SignInMethod,
    User,
)
from app.modules.auth.repository import OAuthAccountRepository
from app.modules.auth.schemas import GoogleSignInRequest
from app.modules.auth.service import AuthService
from app.modules.auth.sessions import IssuedTokens, require_recent_authentication

GOOGLE = OAuthProvider.GOOGLE


class GoogleService:
    def __init__(
        self,
        auth: AuthService,
        db: AsyncSession,
        config: Settings,
        verifier: GoogleIdTokenVerifier | None,
    ) -> None:
        self.auth = auth
        self.db = db
        self.config = config
        self.verifier = verifier
        self.accounts = OAuthAccountRepository(db)

    async def verify(self, id_token: str) -> GoogleIdentity:
        if not self.config.google_auth_enabled or self.verifier is None:
            raise DomainError(ErrorCode.GOOGLE_SIGN_IN_DISABLED)
        try:
            return await self.verifier.verify(id_token)
        except GoogleTokenError as err:
            raise DomainError(ErrorCode.INVALID_GOOGLE_TOKEN) from err
        except GoogleUnavailableError as err:
            raise DomainError(ErrorCode.GOOGLE_UNAVAILABLE) from err

    def fail(self, code: ErrorCode, reason: str, user: User | None = None) -> DomainError:
        """An audited sign-in failure (the audit event commits with the error)."""
        self.auth.audit(
            AuditEventType.LOGIN_FAILED,
            user_id=str(user.id) if user is not None else None,
            method="google",
            reason=reason,
        )
        return DomainError(code, commit=True)

    async def sign_in(self, data: GoogleSignInRequest) -> tuple[IssuedTokens, User]:
        auth = self.auth
        await auth.limiter.hit(limits.GOOGLE_PER_IP, auth.client.ip)
        try:
            identity = await self.verify(data.id_token)
        except DomainError as error:
            if error.code == ErrorCode.INVALID_GOOGLE_TOKEN:
                raise self.fail(ErrorCode.INVALID_GOOGLE_TOKEN, "invalid_token") from error
            raise
        await auth.limiter.hit(limits.GOOGLE_PER_ACCOUNT, identity.subject)

        account = await self.accounts.get(GOOGLE, identity.subject)
        if account is not None and account.state == OAuthLinkState.LINKED:
            user = await auth.users.lock(account.user_id)
            if user is None:  # pragma: no cover - prevented by the foreign key
                raise DomainError(ErrorCode.INVALID_GOOGLE_TOKEN)
            # The link may have been removed while waiting for the user lock.
            current = await self.accounts.get(GOOGLE, identity.subject)
            if (
                current is None
                or current.user_id != user.id
                or current.state != OAuthLinkState.LINKED
            ):
                raise self.fail(ErrorCode.GOOGLE_LINK_REQUIRED, "identity_changed", user)
            self.require_active(user)
            self.mark_verified(user, identity)
        else:
            user = await self.sign_in_by_email(identity, account)

        # The session counts as authenticated when Google issued the token, not now.
        issued = await auth.sessions.start(
            user,
            SignInMethod.GOOGLE,
            auth.client,
            data.device_name,
            authenticated_at=identity.issued_at,
        )
        auth.audit(
            AuditEventType.LOGIN_SUCCEEDED,
            user_id=str(user.id),
            session_id=str(issued.session.id),
            method="google",
        )
        return issued, user

    def require_active(self, user: User) -> None:
        if not user.is_active:
            raise self.fail(ErrorCode.INACTIVE_USER, "inactive", user)

    async def sign_in_by_email(
        self, identity: GoogleIdentity, account: OAuthAccount | None
    ) -> User:
        auth = self.auth
        if not identity.authoritative:
            raise self.fail(ErrorCode.GOOGLE_EMAIL_UNVERIFIED, "email_not_authoritative")
        if account is not None and account.state == OAuthLinkState.UNLINKED:
            raise self.fail(ErrorCode.GOOGLE_LINK_REQUIRED, "identity_unlinked")
        found = await auth.users.get_by_email(identity.email)
        if found is None:
            name = identity.name or identity.email.partition("@")[0]
            created = await auth.users.create(
                identity.email,
                name,
                avatar_url=identity.picture,
                email_verified_at=datetime.now(UTC),
            )
            if created is not None:
                auth.audit(
                    AuditEventType.ACCOUNT_REGISTERED, user_id=str(created.id), method="google"
                )
                await self.link(created, identity, automatic=True)
                return created
            found = await auth.users.get_by_email(identity.email)  # Created concurrently.
            if found is None:  # pragma: no cover - deleted in the same instant
                raise DomainError(ErrorCode.INVALID_GOOGLE_TOKEN)

        user = await auth.users.lock(found.id)
        if user is None:  # pragma: no cover - deleted in the same instant
            raise DomainError(ErrorCode.INVALID_GOOGLE_TOKEN)
        self.require_active(user)  # Before anything changes.
        if user.email_verified_at is None:
            # Google proves control of the inbox: take over the unverified account.
            await auth.claim(user, password_hash=None)
        await self.link(user, identity, automatic=True)
        return user

    async def link(self, user: User, identity: GoogleIdentity, *, automatic: bool) -> None:
        existing = await self.accounts.get(GOOGLE, identity.subject)
        if automatic and existing is not None and existing.state == OAuthLinkState.UNLINKED:
            raise self.fail(ErrorCode.GOOGLE_LINK_REQUIRED, "identity_unlinked", user)
        if existing is not None and existing.user_id != user.id:
            if existing.state == OAuthLinkState.LINKED:
                raise DomainError(ErrorCode.GOOGLE_ACCOUNT_IN_USE)
            await self.accounts.delete(existing)  # A stale, unusable link elsewhere.
            existing = None
        if existing is not None:
            existing.state = OAuthLinkState.LINKED
        else:
            current = await self.accounts.get_for_user(user.id, GOOGLE)
            if current is not None:
                if automatic and current.state == OAuthLinkState.UNLINKED:
                    raise self.fail(ErrorCode.GOOGLE_LINK_REQUIRED, "identity_unlinked", user)
                if current.state == OAuthLinkState.LINKED:
                    raise DomainError(ErrorCode.GOOGLE_ALREADY_LINKED)
                await self.accounts.delete(current)
            if not await self.accounts.add(user.id, GOOGLE, identity.subject):
                raise DomainError(ErrorCode.GOOGLE_ACCOUNT_IN_USE)  # Linked concurrently.
        self.auth.audit(AuditEventType.GOOGLE_LINKED, user_id=str(user.id), automatic=automatic)
        self.auth.mailer.send(Template.GOOGLE_LINKED, user.email, name=user.name)

    def mark_verified(self, user: User, identity: GoogleIdentity) -> None:
        if (
            user.email_verified_at is None
            and identity.authoritative
            and identity.email == user.email.lower()
        ):
            user.email_verified_at = datetime.now(UTC)
            self.auth.audit(AuditEventType.EMAIL_VERIFIED, user_id=str(user.id), method="google")

    async def locked_user(self, context: AuthContext) -> User:
        user = await self.auth.users.lock(context.user.id)
        if user is None:  # pragma: no cover - the session's user row exists
            raise DomainError(ErrorCode.INVALID_TOKEN)
        return user

    async def link_to_current_user(self, context: AuthContext, id_token: str) -> None:
        await self.auth.limiter.hit(limits.GOOGLE_LINK_PER_IP, self.auth.client.ip)
        await self.auth.limiter.hit(limits.GOOGLE_LINK_PER_ACCOUNT, str(context.user.id))
        require_recent_authentication(context.session, self.config)
        user = await self.locked_user(context)
        if user.email_verified_at is None:
            raise DomainError(ErrorCode.EMAIL_VERIFICATION_REQUIRED)
        identity = await self.verify(id_token)
        existing = await self.accounts.get(GOOGLE, identity.subject)
        if (
            existing is not None
            and existing.user_id == user.id
            and existing.state == OAuthLinkState.LINKED
        ):
            return
        await self.link(user, identity, automatic=False)

    async def unlink(self, context: AuthContext) -> bool:
        """Unlink Google and end the sessions it started. True if that included this one."""
        require_recent_authentication(context.session, self.config)
        auth = self.auth
        user = await self.locked_user(context)
        account = await self.accounts.get_for_user(user.id, GOOGLE)
        if account is None or account.state != OAuthLinkState.LINKED:
            raise DomainError(ErrorCode.GOOGLE_NOT_LINKED)
        others = [p for p in await self.accounts.providers_for_user(user.id) if p != GOOGLE]
        has_password = user.hashed_password is not None and user.email_verified_at is not None
        if not has_password and not others:
            raise DomainError(ErrorCode.LAST_SIGN_IN_METHOD)
        # Keep a tombstone: the identity must not be relinked automatically later.
        account.state = OAuthLinkState.UNLINKED
        await auth.tokens.delete_for_user(user.id)
        revoked = await auth.session_rows.revoke_all(
            user.id, SessionRevocation.GOOGLE_UNLINKED, method=SignInMethod.GOOGLE
        )
        auth.audit(
            AuditEventType.GOOGLE_UNLINKED, user_id=str(user.id), sessions_revoked=len(revoked)
        )
        return context.session.id in revoked

    async def reauthenticate(self, context: AuthContext, id_token: str) -> None:
        """Re-authenticate with a Google ID token issued within the re-auth window."""
        auth, user = self.auth, context.user
        await auth.limiter.hit(limits.REAUTH_PER_IP, auth.client.ip)
        await auth.limiter.hit(limits.REAUTH_PER_ACCOUNT, str(user.id))
        try:
            identity: GoogleIdentity | None = await self.verify(id_token)
        except DomainError as error:
            if error.code != ErrorCode.INVALID_GOOGLE_TOKEN:
                raise
            identity = None
        window = timedelta(minutes=self.config.reauthentication_max_age_minutes)
        account = (
            await self.accounts.get(GOOGLE, identity.subject) if identity is not None else None
        )
        if (
            identity is None
            or account is None
            or account.state != OAuthLinkState.LINKED
            or account.user_id != user.id
            or identity.issued_at < datetime.now(UTC) - window
        ):
            auth.audit(
                AuditEventType.REAUTHENTICATION_FAILED,
                user_id=str(user.id),
                session_id=str(context.session.id),
                method="google",
            )
            raise DomainError(ErrorCode.REAUTHENTICATION_FAILED, commit=True)
        # Authenticated when Google issued the token, which may be a few minutes ago.
        context.session.authenticated_at = max(
            context.session.authenticated_at, min(identity.issued_at, datetime.now(UTC))
        )
        auth.audit(
            AuditEventType.REAUTHENTICATED,
            user_id=str(user.id),
            session_id=str(context.session.id),
            method="google",
        )
