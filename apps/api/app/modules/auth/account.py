"""The signed-in user's own account: profile, password, email address and deletion."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.core.audit import AuditEventType
from app.core.errors import DomainError, ErrorCode
from app.core.security import hash_password
from app.integrations.email.templates import Template
from app.modules.auth import limits
from app.modules.auth.deletion import AccountDeletionHook
from app.modules.auth.dependencies import AuthContext
from app.modules.auth.models import AccountTokenPurpose, SessionRevocation, SignInMethod, User
from app.modules.auth.repository import OAuthAccountRepository
from app.modules.auth.schemas import ChangePasswordRequest, UpdateProfileRequest, UserResponse
from app.modules.auth.service import (
    CONFIRM_EMAIL_PATH,
    FORGOT_PASSWORD_PATH,
    AuthService,
    check_current_password,
    describe,
    web_link,
)
from app.modules.auth.sessions import require_recent_authentication


class AccountService:
    def __init__(self, auth: AuthService) -> None:
        self.auth = auth
        self.db = auth.db
        self.config = auth.config
        self.accounts = OAuthAccountRepository(auth.db)

    async def describe_user(self, user: User) -> UserResponse:
        providers = await self.accounts.providers_for_user(user.id)
        return UserResponse.build(user, [SignInMethod(provider) for provider in providers])

    async def update_profile(self, user: User, data: UpdateProfileRequest) -> User:
        if data.name is not None:
            user.name = data.name
        await self.db.flush()
        return user

    async def change_password(self, context: AuthContext, data: ChangePasswordRequest) -> int:
        """Change the password and sign out every other device. Returns how many."""
        auth, user = self.auth, context.user
        if user.hashed_password is None:
            raise DomainError(ErrorCode.PASSWORD_NOT_SET)
        await check_current_password(auth, user, data.current_password, purpose="change_password")
        await auth.policy.check(data.new_password)
        user.hashed_password = await hash_password(data.new_password)
        revoked = await auth.session_rows.revoke_all(
            user.id, SessionRevocation.PASSWORD_CHANGED, keep=context.session.id
        )
        context.session.authenticated_at = datetime.now(UTC)
        auth.audit(
            AuditEventType.PASSWORD_CHANGED,
            user_id=str(user.id),
            session_id=str(context.session.id),
            sessions_revoked=revoked,
        )
        auth.mailer.send(
            Template.PASSWORD_CHANGED,
            user.email,
            name=user.name,
            link=web_link(self.config, FORGOT_PASSWORD_PATH),
        )
        return revoked

    async def request_email_change(self, context: AuthContext, new_email: str) -> None:
        """Email a confirmation link to the new address; the account keeps its email until then."""
        auth, user = self.auth, context.user
        require_recent_authentication(context.session, self.config)
        await auth.limiter.hit(limits.EMAIL_CHANGE_PER_ACCOUNT, str(user.id))
        # Same response either way: this must not reveal which addresses have accounts.
        if new_email == user.email.lower() or await auth.users.get_by_email(new_email) is not None:
            return
        lifetime = timedelta(hours=self.config.email_token_expire_hours)
        token = await auth.emails.issue(user, AccountTokenPurpose.CHANGE_EMAIL, new_email, lifetime)
        auth.mailer.send(
            Template.EMAIL_CHANGE,
            new_email,
            name=user.name,
            link=web_link(self.config, CONFIRM_EMAIL_PATH, token),
            expires=describe(lifetime),
        )
        auth.audit(
            AuditEventType.EMAIL_CHANGE_REQUESTED,
            user_id=str(user.id),
            session_id=str(context.session.id),
        )

    async def confirm_email_change(self, token: str) -> None:
        auth = self.auth
        record = await auth.emails.consume(AccountTokenPurpose.CHANGE_EMAIL, token)
        user = await auth.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise DomainError(ErrorCode.INVALID_OR_EXPIRED_TOKEN)
        owner = await auth.users.get_by_email(record.email)
        if owner is not None and owner.id != user.id:
            raise DomainError(ErrorCode.EMAIL_IN_USE)

        previous = user.email
        user.email = record.email
        user.email_verified_at = datetime.now(UTC)
        try:
            await self.db.flush()
        except IntegrityError as err:  # Taken by a concurrent registration.
            raise DomainError(ErrorCode.EMAIL_IN_USE) from err
        # Links sent to the previous address must not work any more.
        for purpose in (AccountTokenPurpose.VERIFY_EMAIL, AccountTokenPurpose.RESET_PASSWORD):
            await auth.emails.tokens.delete_for_user(user.id, purpose)
        auth.audit(AuditEventType.EMAIL_CHANGED, user_id=str(user.id))
        auth.mailer.send(Template.EMAIL_CHANGED, previous, name=user.name)

    async def delete_account(self, context: AuthContext, hooks: list[AccountDeletionHook]) -> None:
        auth, user = self.auth, context.user
        require_recent_authentication(context.session, self.config)
        for hook in hooks:
            await hook.check(self.db, user)
        for hook in hooks:
            await hook.before_delete(self.db, user)
        email, name = user.email, user.name
        # Audit rows have no foreign key; they stay as pseudonymous security records.
        auth.audit(
            AuditEventType.ACCOUNT_DELETED,
            user_id=str(user.id),
            session_id=str(context.session.id),
        )
        # Cascades remove sessions and refresh tokens, linked identities, emailed
        # tokens, idempotency records and the user's items.
        await auth.users.delete(user)
        auth.mailer.send(Template.ACCOUNT_DELETED, email, name=name)
