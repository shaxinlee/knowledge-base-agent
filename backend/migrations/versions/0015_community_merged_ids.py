"""Add merged_summary_ids to track incremental community summary merges.

Revision ID: 0015_community_merged_summary_ids
Revises: 0014_knowledge_graph
Create Date: 2026-06-29 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0015_community_merged_ids"
down_revision: str | None = "0014_knowledge_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_base_community_summaries",
        sa.Column(
            "merged_summary_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("knowledge_base_community_summaries", "merged_summary_ids")
