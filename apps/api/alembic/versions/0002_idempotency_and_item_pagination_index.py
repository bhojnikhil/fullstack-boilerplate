"""idempotency and item pagination index

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24 10:11:04.503791

"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Do the non-transactional step first. A failed concurrent build can leave
    # an invalid index behind, and later DDL can fail after the index was built.
    with op.get_context().autocommit_block():
        drop_items_index()
        op.create_index(
            "ix_items_user_created_id",
            "items",
            ["user_id", "created_at", "id"],
            postgresql_concurrently=True,
        )
    op.create_table(
        "idempotency_records",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.SmallInteger(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "key"),
    )
    op.create_index(
        "ix_idempotency_records_expires_at", "idempotency_records", ["expires_at"], unique=False
    )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        drop_items_index()
    op.drop_index("ix_idempotency_records_expires_at", table_name="idempotency_records")
    op.drop_table("idempotency_records")


def drop_items_index() -> None:
    op.drop_index(
        "ix_items_user_created_id", table_name="items", if_exists=True, postgresql_concurrently=True
    )
