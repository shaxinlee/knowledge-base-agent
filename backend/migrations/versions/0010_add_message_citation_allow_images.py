"""Add message citation image display flag.

Revision ID: 0010_allow_images
Revises: 0009_create_feedback
Create Date: 2026-06-08 00:00:10.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0010_allow_images"
down_revision: str | None = "0009_create_feedback"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "message_citations",
        sa.Column("allow_images", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.alter_column("message_citations", "allow_images", server_default=None)


def downgrade() -> None:
    op.drop_column("message_citations", "allow_images")
