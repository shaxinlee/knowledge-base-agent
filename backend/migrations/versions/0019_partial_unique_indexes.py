"""Replace email/username unique constraints with partial indexes (ignore soft-deleted users).

Revision ID: 0019_partial_unique_indexes
Revises: 0018_user_session_id
Create Date: 2026-07-01 13:15:00.000000
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0019_partial_unique_indexes"
down_revision: str | None = "0018_user_session_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.drop_constraint("uq_users_username", "users", type_="unique")

    op.create_index(
        "uq_users_email_active",
        "users",
        ["email"],
        unique=True,
        postgresql_where=text("deleted_at IS NULL"),
    )
    op.create_index(
        "uq_users_username_active",
        "users",
        ["username"],
        unique=True,
        postgresql_where=text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_username_active", table_name="users")
    op.drop_index("uq_users_email_active", table_name="users")

    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_unique_constraint("uq_users_email", "users", ["email"])
