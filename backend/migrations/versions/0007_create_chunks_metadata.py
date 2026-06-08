"""Create chunks metadata.

Revision ID: 0007_chunks_metadata
Revises: 0006_document_blocks
Create Date: 2026-06-06 00:00:06.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0007_chunks_metadata"
down_revision: str | None = "0006_document_blocks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunks_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("slide_number", sa.Integer(), nullable=True),
        sa.Column("sheet_name", sa.String(length=255), nullable=True),
        sa.Column("row_start", sa.Integer(), nullable=True),
        sa.Column("row_end", sa.Integer(), nullable=True),
        sa.Column("heading_path", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_locator", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name=op.f("fk_chunks_metadata_file_id_files")
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_chunks_metadata_knowledge_base_id_knowledge_bases"),
        ),
        sa.ForeignKeyConstraint(
            ["parse_job_id"],
            ["parse_jobs.id"],
            name=op.f("fk_chunks_metadata_parse_job_id_parse_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks_metadata")),
    )
    op.create_index(
        "idx_chunks_kb_active",
        "chunks_metadata",
        ["knowledge_base_id", "is_active"],
    )
    op.create_index("idx_chunks_file", "chunks_metadata", ["file_id"])
    op.create_index("idx_chunks_parse_job", "chunks_metadata", ["parse_job_id"])
    op.create_index(
        "idx_chunks_tsv",
        "chunks_metadata",
        ["tsv"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("idx_chunks_tsv", table_name="chunks_metadata", postgresql_using="gin")
    op.drop_index("idx_chunks_parse_job", table_name="chunks_metadata")
    op.drop_index("idx_chunks_file", table_name="chunks_metadata")
    op.drop_index("idx_chunks_kb_active", table_name="chunks_metadata")
    op.drop_table("chunks_metadata")
