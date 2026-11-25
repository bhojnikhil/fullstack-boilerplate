"""auth sessions, emailed tokens, audit log and rate limits

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-24 15:23:43.411883

- Adds device sessions with refresh-token rotation, single-use emailed tokens,
  the audit log and Postgres-backed rate-limit windows.
- Adds users.email_verified_at. Existing users start unverified and cannot sign in
  with a password until they prove they own the address (verification link or reset).
- Adds a case-insensitive unique index on users.email, built concurrently. The
  exact-case ix_users_email stays for now.
- Drops the Google access/refresh tokens and their expiry from oauth_accounts
  (stored in plaintext by the removed redirect flow). They cannot be restored.
- Allows one Google identity per user, and records each link's state. Links that the
  removed flow attached to password accounts by matching emails become "unconfirmed":
  the two credentials may belong to different people, so the link is not usable until
  Google or the inbox proves ownership again.

Before any DDL, the upgrade stops with instructions if two accounts differ only by
letter case or a user has more than one Google identity. This release drops columns
the previous one reads and does not accept its tokens: stop the old API before
migrating (a coordinated cutover, not a rolling deploy).
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    require_case_insensitive_unique_emails()
    require_one_identity_per_provider()
    # Non-transactional step first, as in 0002: a failed concurrent build can leave an
    # invalid index, which the drop below removes when the upgrade is retried.
    with op.get_context().autocommit_block():
        drop_email_lower_index()
        op.create_index(
            "ux_users_email_lower",
            "users",
            [sa.literal_column("lower(email)")],
            unique=True,
            postgresql_concurrently=True,
        )

    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint(
        "uq_oauth_accounts_user_id_provider", "oauth_accounts", ["user_id", "provider"]
    )
    op.add_column(
        "oauth_accounts",
        sa.Column("state", sa.String(length=16), nullable=False, server_default="linked"),
    )
    op.alter_column("oauth_accounts", "state", server_default=None)
    # The removed flow linked Google to any account with the same email. On accounts
    # that also have a password, the two may belong to different people.
    op.execute(
        "UPDATE oauth_accounts SET state = 'unconfirmed' WHERE user_id IN "
        "(SELECT id FROM users WHERE hashed_password IS NOT NULL)"
    )
    op.drop_column("oauth_accounts", "access_token")
    op.drop_column("oauth_accounts", "refresh_token")
    op.drop_column("oauth_accounts", "expires_at")

    op.create_table(
        "auth_sessions",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("sign_in_method", sa.String(length=16), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("device_name", sa.String(length=100), nullable=True),
        sa.Column("user_agent", sa.String(length=100), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=32), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_auth_sessions_user_created_id",
        "auth_sessions",
        ["user_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("session_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_refresh_tokens_session_id"), "refresh_tokens", ["session_id"], unique=False
    )
    op.create_table(
        "account_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("pending_name", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_account_tokens_user_id_purpose", "account_tokens", ["user_id", "purpose"], unique=False
    )
    op.create_table(
        "audit_events",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("event", sa.String(length=64), nullable=False),
        # No foreign keys: events outlive deleted accounts as pseudonymous records.
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("session_id", sa.UUID(), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=100), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_events_created_at", "audit_events", ["created_at"], unique=False)
    op.create_index(
        "ix_audit_events_user_id_created_at",
        "audit_events",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "rate_limits",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("resets_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_rate_limits_resets_at", "rate_limits", ["resets_at"], unique=False)


def downgrade() -> None:
    with op.get_context().autocommit_block():
        drop_email_lower_index()
    op.drop_index("ix_rate_limits_resets_at", table_name="rate_limits")
    op.drop_table("rate_limits")
    op.drop_index("ix_audit_events_user_id_created_at", table_name="audit_events")
    op.drop_index("ix_audit_events_created_at", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_account_tokens_user_id_purpose", table_name="account_tokens")
    op.drop_table("account_tokens")
    op.drop_index(op.f("ix_refresh_tokens_session_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_index("ix_auth_sessions_user_created_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    # The dropped Google tokens are gone; the restored columns are empty.
    op.add_column(
        "oauth_accounts",
        sa.Column("access_token", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.alter_column("oauth_accounts", "access_token", server_default=None)
    op.add_column("oauth_accounts", sa.Column("refresh_token", sa.Text(), nullable=True))
    op.add_column(
        "oauth_accounts", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.execute("DELETE FROM oauth_accounts WHERE state <> 'linked'")
    op.drop_column("oauth_accounts", "state")
    op.drop_constraint("uq_oauth_accounts_user_id_provider", "oauth_accounts", type_="unique")
    op.drop_column("users", "email_verified_at")


def drop_email_lower_index() -> None:
    op.drop_index(
        "ux_users_email_lower", table_name="users", if_exists=True, postgresql_concurrently=True
    )


def require_one_identity_per_provider() -> None:
    if op.get_context().as_sql:
        return
    duplicated = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM (SELECT 1 FROM oauth_accounts GROUP BY user_id, provider "
            "HAVING count(*) > 1) AS duplicated"
        )
    )
    if duplicated:
        raise RuntimeError(
            f"{duplicated} user(s) have more than one linked identity from the same provider. "
            "Keep one link per user and provider (delete the others), then rerun the "
            "migration. List them with: SELECT user_id, provider, count(*) FROM "
            "oauth_accounts GROUP BY 1, 2 HAVING count(*) > 1"
        )


def require_case_insensitive_unique_emails() -> None:
    if op.get_context().as_sql:
        return  # Offline SQL generation cannot inspect data.
    duplicates = op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM (SELECT 1 FROM users GROUP BY lower(email) "
            "HAVING count(*) > 1) AS duplicated"
        )
    )
    if duplicates:
        raise RuntimeError(
            f"{duplicates} email address(es) belong to more than one account when letter case "
            "is ignored. Merge or rename those accounts, then rerun the migration. List them "
            "with: SELECT lower(email) FROM users GROUP BY 1 HAVING count(*) > 1"
        )
