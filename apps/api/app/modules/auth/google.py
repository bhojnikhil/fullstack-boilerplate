"""Sign in with Google (ID tokens), plus explicit linking and unlinking.

Linking rules (pre-account-takeover defense):
- A Google identity already linked to a user signs in as that user.
- Otherwise Google must report the email as verified. A new email creates a user.
- An existing account is linked automatically only when its own email is verified.
  If it is not, the person must sign in to that account (or reset its password,
  which proves control of the inbox) and link Google explicitly. Without this, an
  attacker could pre-register someone's email with a password and keep access
  after the owner signs in with Google.

Other providers (e.g. Sign in with Apple) would follow the same shape: a verifier
in ``app.integrations`` and a service like this one keyed by ``OAuthProvider``.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import AuditEventType
from app.core.config import Settings
from app.core.errors import DomainError, ErrorCode
from app.integrations.google_id_token import (
    GoogleIdentity,
    GoogleIdTokenVerifier,
    GoogleTokenError,
    GoogleUnavailableError,
)
from app.modules.auth import limits
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.models import OAuthAccount, OAuthProvider, SignInMethod, User
from app.modules.auth.repository import OAuthAccountRepository
from app.modules.auth.schemas import GoogleSignInRequest
from app.modules.auth.service import AuthService
from app.modules.auth.sessions import IssuedTokens, require_recent_authentication


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

    async def sign_in(self, data: GoogleSignInRequest) -> tuple[IssuedTokens, User]:
        auth, client = self.auth, self.auth.client
        await auth.limiter.hit(limits.GOOGLE_PER_IP, client.ip)
        identity = await self.verify(data.id_token)
        await auth.limiter.hit(limits.GOOGLE_PER_ACCOUNT, identity.subject)

        account = await self.accounts.get(OAuthProvider.GOOGLE, identity.subject)
        if account is not None:
            user = await auth.users.get_by_id(account.user_id)
            if user is None:  # pragma: no cover - prevented by the foreign key
                raise DomainError(ErrorCode.INVALID_GOOGLE_TOKEN)
        else:
            user = await self.find_or_create_user(identity)

        if not user.is_active:
            auth.audit(AuditEventType.LOGIN_FAILED, user_id=str(user.id), reason="inactive")
            raise DomainError(ErrorCode.INACTIVE_USER, commit=True)
        self.mark_verified(user, identity)
        issued = await auth.sessions.start(user, SignInMethod.GOOGLE, client, data.device_name)
        auth.audit(
            AuditEventType.LOGIN_SUCCEEDED,
            user_id=str(user.id),
            session_id=str(issued.session.id),
            method="google",
        )
        return issued, user

    async def find_or_create_user(self, identity: GoogleIdentity) -> User:
        auth = self.auth
        if not identity.email_verified:
            # Never create or link an account from an address Google has not verified.
            auth.audit(AuditEventType.LOGIN_FAILED, method="google", reason="email_unverified")
            raise DomainError(ErrorCode.GOOGLE_EMAIL_UNVERIFIED, commit=True)

        email = identity.email.lower()
        user = await auth.users.get_by_email(email)
        if user is None:
            name = identity.name or email.partition("@")[0]
            user = await auth.users.create(
                email,
                name,
                avatar_url=identity.picture,
                email_verified_at=datetime.now(UTC),
            )
            if user is not None:
                auth.audit(AuditEventType.ACCOUNT_REGISTERED, user_id=str(user.id), method="google")
            else:
                # Registered concurrently: treat it like any existing account.
                user = await auth.users.get_by_email(email)
                if user is None:  # pragma: no cover - deleted in the same instant
                    raise DomainError(ErrorCode.INVALID_GOOGLE_TOKEN)
                self.require_auto_link(user)
        else:
            self.require_auto_link(user)
        await self.link(user, identity, automatic=True)
        return user

    def require_auto_link(self, user: User) -> None:
        # Google proved the caller owns this email, so naming the conflict leaks nothing.
        if user.email_verified_at is None:
            self.auth.audit(
                AuditEventType.LOGIN_FAILED,
                user_id=str(user.id),
                method="google",
                reason="link_required",
            )
            raise DomainError(ErrorCode.GOOGLE_LINK_REQUIRED, commit=True)

    async def link(self, user: User, identity: GoogleIdentity, *, automatic: bool) -> None:
        inserted = await self.db.scalar(
            insert(OAuthAccount)
            .values(
                user_id=user.id,
                provider=OAuthProvider.GOOGLE,
                provider_account_id=identity.subject,
            )
            .on_conflict_do_nothing()
            .returning(OAuthAccount.id)
        )
        if inserted is None:
            existing = await self.accounts.get(OAuthProvider.GOOGLE, identity.subject)
            if existing is not None and existing.user_id == user.id:
                return  # Linked by a concurrent request.
            code = (
                ErrorCode.GOOGLE_ACCOUNT_IN_USE
                if existing is not None
                else ErrorCode.GOOGLE_ALREADY_LINKED
            )
            raise DomainError(code)
        self.auth.audit(AuditEventType.GOOGLE_LINKED, user_id=str(user.id), automatic=automatic)

    def mark_verified(self, user: User, identity: GoogleIdentity) -> None:
        if (
            user.email_verified_at is None
            and identity.email_verified
            and identity.email.lower() == user.email.lower()
        ):
            user.email_verified_at = datetime.now(UTC)
            self.auth.audit(AuditEventType.EMAIL_VERIFIED, user_id=str(user.id), method="google")

    async def link_to_current_user(self, context: AuthContext, id_token: str) -> None:
        require_recent_authentication(context.session, self.config)
        identity = await self.verify(id_token)
        user = context.user
        existing = await self.accounts.get(OAuthProvider.GOOGLE, identity.subject)
        if existing is not None:
            if existing.user_id == user.id:
                return
            raise DomainError(ErrorCode.GOOGLE_ACCOUNT_IN_USE)
        if await self.accounts.get_for_user(user.id, OAuthProvider.GOOGLE) is not None:
            raise DomainError(ErrorCode.GOOGLE_ALREADY_LINKED)
        await self.link(user, identity, automatic=False)
        self.mark_verified(user, identity)

    async def unlink(self, context: AuthContext) -> None:
        require_recent_authentication(context.session, self.config)
        user = context.user
        account = await self.accounts.get_for_user(user.id, OAuthProvider.GOOGLE)
        if account is None:
            raise DomainError(ErrorCode.GOOGLE_NOT_LINKED)
        others = [
            provider
            for provider in await self.accounts.providers_for_user(user.id)
            if provider != OAuthProvider.GOOGLE
        ]
        if user.hashed_password is None and not others:
            raise DomainError(ErrorCode.LAST_SIGN_IN_METHOD)
        await self.accounts.delete(account)
        self.auth.audit(AuditEventType.GOOGLE_UNLINKED, user_id=str(user.id))

    async def reauthenticate(self, context: AuthContext, id_token: str) -> None:
        """Re-authenticate with a Google ID token issued within the re-auth window."""
        auth, user = self.auth, context.user
        await auth.limiter.hit(limits.REAUTH_PER_ACCOUNT, str(user.id))
        try:
            identity = await self.verify(id_token)
        except DomainError as error:
            if error.code != ErrorCode.INVALID_GOOGLE_TOKEN:
                raise
            identity = None
        window = timedelta(minutes=self.config.reauthentication_max_age_minutes)
        account = (
            await self.accounts.get(OAuthProvider.GOOGLE, identity.subject) if identity else None
        )
        if (
            identity is None
            or account is None
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
        context.session.authenticated_at = datetime.now(UTC)
        auth.audit(
            AuditEventType.REAUTHENTICATED,
            user_id=str(user.id),
            session_id=str(context.session.id),
            method="google",
        )
