"""workspaces, memberships, invitations, workspace-scoped items and row-level security

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-25 09:00:00.000000

- Adds workspaces, memberships and invitations. One owner per workspace is enforced by
  a unique partial index and by a deferred composite foreign key from the workspace to
  its owner's membership (see app/modules/workspaces/models.py).
- Items move from users to workspaces. Every user who has items gets a personal
  workspace ("Personal", USD, UTC) that they own, and their items move into it.
  ``items.user_id`` becomes the nullable ``items.created_by_id``.
- Enables and FORCES row-level security on workspaces, memberships, invitations and
  items. Policies read the ``app.user_id``, ``app.workspace_id`` and
  ``app.invitation_hash`` settings (app/core/rls.py).
- Creates the application role (default ``app_user``, ``APP_DB_ROLE``) as NOLOGIN when
  it does not exist and grants it table access. The role has no password and cannot
  sign in until an operator runs ``ALTER ROLE ... LOGIN PASSWORD`` (or ran
  scripts/db/bootstrap-app-role.sql first). A role that is a superuser or has BYPASSRLS
  is refused, because row-level security would not apply to it.

Run migrations as the table owner (MIGRATION_DATABASE_URL). The owner needs CREATEROLE
only when the application role does not exist yet.
"""

import re

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TENANT_TABLES = ("workspaces", "memberships", "invitations", "items")
WORKSPACE = "NULLIF(current_setting('app.workspace_id', true), '')::uuid"
USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
INVITATION = "NULLIF(current_setting('app.invitation_hash', true), '')"

# (table, command, USING, WITH CHECK). Commands without USING/CHECK use None.
POLICIES: list[tuple[str, str, str, str | None, str | None]] = [
    (
        "workspaces",
        "select",
        "workspaces_select",
        f"id = {WORKSPACE} OR EXISTS (SELECT 1 FROM memberships m "
        f"WHERE m.workspace_id = workspaces.id AND m.user_id = {USER})",
        None,
    ),
    ("workspaces", "insert", "workspaces_insert", None, f"id = {WORKSPACE}"),
    ("workspaces", "update", "workspaces_update", f"id = {WORKSPACE}", f"id = {WORKSPACE}"),
    ("workspaces", "delete", "workspaces_delete", f"id = {WORKSPACE}", None),
    (
        "memberships",
        "select",
        "memberships_select",
        f"user_id = {USER} OR workspace_id = {WORKSPACE}",
        None,
    ),
    # A membership is created for oneself, in the active workspace, either as the
    # owner of a workspace being created or by presenting a usable invitation.
    (
        "memberships",
        "insert",
        "memberships_insert",
        None,
        f"user_id = {USER} AND workspace_id = {WORKSPACE} AND (role = 'owner' OR EXISTS ("
        "SELECT 1 FROM invitations i WHERE i.workspace_id = memberships.workspace_id "
        f"AND i.token_hash = {INVITATION} AND i.role = memberships.role "
        "AND i.accepted_at IS NULL AND i.revoked_at IS NULL AND i.expires_at > now()))",
    ),
    (
        "memberships",
        "update",
        "memberships_update",
        f"workspace_id = {WORKSPACE}",
        f"workspace_id = {WORKSPACE}",
    ),
    ("memberships", "delete", "memberships_delete", f"workspace_id = {WORKSPACE}", None),
    (
        "invitations",
        "select",
        "invitations_select",
        f"workspace_id = {WORKSPACE} OR token_hash = {INVITATION}",
        None,
    ),
    ("invitations", "insert", "invitations_insert", None, f"workspace_id = {WORKSPACE}"),
    (
        "invitations",
        "update",
        "invitations_update",
        f"workspace_id = {WORKSPACE} OR token_hash = {INVITATION}",
        f"workspace_id = {WORKSPACE} OR token_hash = {INVITATION}",
    ),
    ("invitations", "delete", "invitations_delete", f"workspace_id = {WORKSPACE}", None),
    (
        "items",
        "all",
        "items_workspace",
        f"workspace_id = {WORKSPACE} AND EXISTS (SELECT 1 FROM memberships m "
        f"WHERE m.workspace_id = items.workspace_id AND m.user_id = {USER})",
        f"workspace_id = {WORKSPACE} AND EXISTS (SELECT 1 FROM memberships m "
        f"WHERE m.workspace_id = items.workspace_id AND m.user_id = {USER})",
    ),
]


def app_role() -> str:
    from app.core.config import DatabaseSettings

    role = DatabaseSettings().app_db_role
    if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", role):  # pragma: no cover - validated
        raise RuntimeError("APP_DB_ROLE must be a lowercase PostgreSQL role name")
    return role


def create_tables() -> None:
    op.create_table(
        "workspaces",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("slug", sa.String(length=48), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column(
            "owner_role", sa.String(length=5), server_default=sa.text("'owner'"), nullable=False
        ),
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
        sa.CheckConstraint("owner_role = 'owner'", name="ck_workspaces_owner_role"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "memberships",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
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
        sa.CheckConstraint("role IN ('owner', 'admin', 'member')", name="ck_memberships_role"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_memberships_workspace_user"),
        sa.UniqueConstraint(
            "workspace_id", "user_id", "role", name="uq_memberships_workspace_user_role"
        ),
    )
    op.create_index(
        "uq_memberships_one_owner",
        "memberships",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )
    op.create_index("ix_memberships_user_id", "memberships", ["user_id"])
    op.create_table(
        "invitations",
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_id", sa.UUID(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invited_by_id", sa.UUID(), nullable=True),
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
        sa.CheckConstraint("role IN ('admin', 'member')", name="ck_invitations_role"),
        sa.CheckConstraint(
            "accepted_at IS NULL OR revoked_at IS NULL", name="ck_invitations_one_outcome"
        ),
        sa.ForeignKeyConstraint(["accepted_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invited_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_invitations_workspace_created_id",
        "invitations",
        ["workspace_id", "created_at", "id"],
    )


def move_items_into_workspaces() -> None:
    op.add_column("items", sa.Column("workspace_id", sa.UUID(), nullable=True))
    # Each user with items gets a personal workspace they own. The deferred owner key
    # does not exist yet, so these inserts leave no pending trigger events behind.
    op.execute(
        """
        INSERT INTO workspaces (id, name, slug, currency, timezone, owner_id, owner_role)
        SELECT gen_random_uuid(), 'Personal', 'personal-' || replace(user_id::text, '-', ''),
               'USD', 'UTC', user_id, 'owner'
        FROM (SELECT DISTINCT user_id FROM items) AS authors
        """
    )
    op.execute(
        """
        INSERT INTO memberships (id, workspace_id, user_id, role)
        SELECT gen_random_uuid(), id, owner_id, 'owner' FROM workspaces
        """
    )
    op.execute(
        "UPDATE items SET workspace_id = w.id FROM workspaces w WHERE w.owner_id = items.user_id"
    )
    op.alter_column("items", "workspace_id", nullable=False)
    op.create_foreign_key(
        "items_workspace_id_fkey",
        "items",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_index("ix_items_user_created_id", table_name="items")
    op.drop_constraint("items_user_id_fkey", "items", type_="foreignkey")
    op.alter_column("items", "user_id", new_column_name="created_by_id", nullable=True)
    op.create_foreign_key(
        "items_created_by_id_fkey", "items", "users", ["created_by_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_items_workspace_created_id", "items", ["workspace_id", "created_at", "id"])


def enable_row_level_security() -> None:
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # FORCE: the table owner is bound by the policies too, not only the app role.
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for table, command, name, using, check in POLICIES:
        clauses = f"FOR {command.upper()}"
        if using is not None:
            clauses += f" USING ({using})"
        if check is not None:
            clauses += f" WITH CHECK ({check})"
        op.execute(f"CREATE POLICY {name} ON {table} {clauses}")


def grant_application_role(role: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '{role}') THEN
                CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
            ELSIF EXISTS (
                SELECT FROM pg_roles WHERE rolname = '{role}' AND (rolsuper OR rolbypassrls)
            ) THEN
                RAISE EXCEPTION
                    'Role {role} is a superuser or has BYPASSRLS, so row-level security would '
                    'not apply to it. Use a plain login role for DATABASE_URL.';
            END IF;
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO {role}', current_schema());
            EXECUTE format(
                'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO {role}',
                current_schema()
            );
            -- The API reads the migration revision (/ready) but never writes it.
            EXECUTE format(
                'REVOKE INSERT, UPDATE, DELETE ON %I.alembic_version FROM {role}',
                current_schema()
            );
            -- Tables created by later migrations (run by this role) are granted too.
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
                'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}',
                current_schema()
            );
        END
        $$
        """
    )


def upgrade() -> None:
    role = app_role()
    create_tables()
    move_items_into_workspaces()
    # Created last: the deferred key would otherwise hold pending events during the
    # inserts above, and ALTER TABLE refuses to run while events are pending.
    op.create_foreign_key(
        "fk_workspaces_owner_membership",
        "workspaces",
        "memberships",
        ["id", "owner_id", "owner_role"],
        ["workspace_id", "user_id", "role"],
        deferrable=True,
        initially="DEFERRED",
    )
    enable_row_level_security()
    grant_application_role(role)


def downgrade() -> None:
    for table, _command, name, _using, _check in POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Items go back to their authors. Items whose author is gone go to the workspace owner.
    op.drop_index("ix_items_workspace_created_id", table_name="items")
    op.drop_constraint("items_created_by_id_fkey", "items", type_="foreignkey")
    op.execute(
        "UPDATE items SET created_by_id = w.owner_id FROM workspaces w "
        "WHERE w.id = items.workspace_id AND items.created_by_id IS NULL"
    )
    op.alter_column("items", "created_by_id", new_column_name="user_id", nullable=False)
    op.create_foreign_key(
        "items_user_id_fkey", "items", "users", ["user_id"], ["id"], ondelete="CASCADE"
    )
    op.drop_constraint("items_workspace_id_fkey", "items", type_="foreignkey")
    op.drop_column("items", "workspace_id")
    op.create_index("ix_items_user_created_id", "items", ["user_id", "created_at", "id"])

    op.drop_constraint("fk_workspaces_owner_membership", "workspaces", type_="foreignkey")
    op.drop_table("invitations")
    op.drop_table("memberships")
    op.drop_table("workspaces")
