"""Create document blocks.

Revision ID: 0006_document_blocks
Revises: 0005_files_parse_jobs
Create Date: 2026-06-06 00:00:05.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_document_blocks"
down_revision: str | None = "0005_files_parse_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_index", sa.Integer(), nullable=False),
        sa.Column("block_type", sa.String(length=50), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("row_start", sa.Integer(), nullable=True),
        sa.Column("row_end", sa.Integer(), nullable=True),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name=op.f("fk_document_blocks_file_id_files")
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_document_blocks_knowledge_base_id_knowledge_bases"),
        ),
        sa.ForeignKeyConstraint(
            ["parse_job_id"],
            ["parse_jobs.id"],
            name=op.f("fk_document_blocks_parse_job_id_parse_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_blocks")),
    )
    op.create_index(
        "ix_document_blocks_file_parse_job",
        "document_blocks",
        ["file_id", "parse_job_id"],
    )
    op.create_index(
        "ix_document_blocks_kb_file",
        "document_blocks",
        ["knowledge_base_id", "file_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_blocks_kb_file", table_name="document_blocks")
    op.drop_index("ix_document_blocks_file_parse_job", table_name="document_blocks")
    op.drop_table("document_blocks")
