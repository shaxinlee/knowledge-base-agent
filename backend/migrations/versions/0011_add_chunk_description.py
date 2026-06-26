"""Add chunk description.

Revision ID: 0011_chunk_description
Revises: 0010_allow_images
Create Date: 2026-06-09 00:00:11.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0011_chunk_description"
down_revision: str | None = "0010_allow_images"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("chunks_metadata", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks_metadata", "description")
