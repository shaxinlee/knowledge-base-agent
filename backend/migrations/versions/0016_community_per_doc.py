"""Add per_document JSONB column for structured community summaries.

Revision ID: 0016_community_per_doc
Revises: 0015_community_merged_ids
Create Date: 2026-06-29 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0016_community_per_doc"
down_revision: str | None = "0015_community_merged_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base_community_summaries",
        sa.Column(
            "per_document",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_base_community_summaries", "per_document")
