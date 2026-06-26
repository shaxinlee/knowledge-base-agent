"""Create chunk knowledge extractions and document summaries.

Revision ID: 0013_document_summaries
Revises: 0012_message_attachments
Create Date: 2026-06-21 00:00:13.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0013_document_summaries"
down_revision: str | None = "0012_message_attachments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "document_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="20", nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("chunk_total", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_succeeded", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunk_failed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_chunk_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("chunk_prompt_version", sa.String(length=100), nullable=False),
        sa.Column("document_prompt_version", sa.String(length=100), nullable=False),
        sa.Column("reduction_level", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            (
                "status in ('pending', 'running', 'completed', 'partially_completed', "
                "'failed', 'not_ready')"
            ),
            name=op.f("ck_document_summaries_document_summary_status_valid"),
        ),
        sa.CheckConstraint(
            "priority >= 0",
            name=op.f("ck_document_summaries_document_summary_priority_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name=op.f("fk_document_summaries_file_id_files")
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_document_summaries_knowledge_base_id_knowledge_bases"),
        ),
        sa.ForeignKeyConstraint(
            ["parse_job_id"],
            ["parse_jobs.id"],
            name=op.f("fk_document_summaries_parse_job_id_parse_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_summaries")),
        sa.UniqueConstraint(
            "file_id", "parse_job_id", name="uq_document_summaries_file_parse_job"
        ),
    )
    op.create_index(
        "idx_document_summaries_queue",
        "document_summaries",
        ["status", "priority", "created_at"],
    )
    op.create_index(
        "idx_document_summaries_file",
        "document_summaries",
        ["file_id", "created_at"],
    )
    op.create_table(
        "chunk_knowledge_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("extraction", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("short_summary", sa.Text(), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status in ('pending', 'running', 'completed', 'failed')",
            name=op.f("ck_chunk_knowledge_extractions_chunk_extraction_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["chunk_id"],
            ["chunks_metadata.id"],
            name=op.f("fk_chunk_knowledge_extractions_chunk_id_chunks_metadata"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_chunk_knowledge_extractions_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["parse_job_id"],
            ["parse_jobs.id"],
            name=op.f("fk_chunk_knowledge_extractions_parse_job_id_parse_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk_knowledge_extractions")),
        sa.UniqueConstraint("chunk_id", name="uq_chunk_knowledge_extractions_chunk_id"),
    )
    op.create_index(
        "idx_chunk_extractions_file_job_status",
        "chunk_knowledge_extractions",
        ["file_id", "parse_job_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_chunk_extractions_file_job_status",
        table_name="chunk_knowledge_extractions",
    )
    op.drop_table("chunk_knowledge_extractions")
    op.drop_index("idx_document_summaries_file", table_name="document_summaries")
    op.drop_index("idx_document_summaries_queue", table_name="document_summaries")
    op.drop_table("document_summaries")
