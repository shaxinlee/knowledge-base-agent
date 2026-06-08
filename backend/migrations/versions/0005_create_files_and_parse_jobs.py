"""Create files and parse jobs.

Revision ID: 0005_files_parse_jobs
Revises: 0004_kb_audit
Create Date: 2026-06-06 00:00:04.000000

"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_files_parse_jobs"
down_revision: str | None = "0004_kb_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "files",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_ext", sa.String(length=20), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("storage_bucket", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("latest_parse_job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            (
                "status in ('uploaded', 'queued', 'processing', 'indexed', "
                "'partially_indexed', 'failed', 'deleting', 'deleted')"
            ),
            name=op.f("ck_files_file_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_files_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_files_knowledge_base_id_knowledge_bases"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_files")),
    )
    op.create_table(
        "parse_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("logs", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
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
                "status in ('queued', 'parsing', 'normalizing', 'chunking', "
                "'embedding', 'indexing', 'indexed', 'partially_indexed', "
                "'failed', 'cancelled')"
            ),
            name=op.f("ck_parse_jobs_parse_job_status_valid"),
        ),
        sa.CheckConstraint(
            "progress >= 0 and progress <= 100",
            name=op.f("ck_parse_jobs_parse_job_progress_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_parse_jobs_created_by_users")
        ),
        sa.ForeignKeyConstraint(
            ["file_id"], ["files.id"], name=op.f("fk_parse_jobs_file_id_files")
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_parse_jobs_knowledge_base_id_knowledge_bases"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_parse_jobs")),
    )
    op.create_index(
        "uq_files_kb_filename_active",
        "files",
        ["knowledge_base_id", "file_name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_files_kb_status_deleted_at",
        "files",
        ["knowledge_base_id", "status", "deleted_at"],
    )
    op.create_index(
        "ix_files_kb_hash_active",
        "files",
        ["knowledge_base_id", "file_hash"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_parse_jobs_file_created_at",
        "parse_jobs",
        ["file_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_parse_jobs_file_created_at", table_name="parse_jobs")
    op.drop_index("ix_files_kb_hash_active", table_name="files")
    op.drop_index("ix_files_kb_status_deleted_at", table_name="files")
    op.drop_index("uq_files_kb_filename_active", table_name="files")
    op.drop_table("parse_jobs")
    op.drop_table("files")
