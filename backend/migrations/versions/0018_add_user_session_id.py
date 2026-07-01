"""Add session_id column to users table.

Revision ID: 0018_user_session_id
Revises: 0017_chunk_knowledge_graph
Create Date: 2026-07-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_user_session_id"
down_revision: str | None = "0017_chunk_knowledge_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_id", sa.String(length=36), nullable=True),
    )
    op.create_index("uq_users_session_id", "users", ["session_id"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_session_id", table_name="users")
    op.drop_column("users", "session_id")
