"""Create document relation graph and community summaries.

Revision ID: 0014_knowledge_graph
Revises: 0013_document_summaries
Create Date: 2026-06-21 00:00:14.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0014_knowledge_graph"
down_revision: str | None = "0013_document_summaries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_graph_state",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_key", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("document_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("relation_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            name=op.f("ck_knowledge_graph_state_knowledge_graph_state_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_knowledge_graph_state")),
        sa.UniqueConstraint("state_key", name="uq_knowledge_graph_state_state_key"),
    )
    op.create_table(
        "knowledge_base_community_summaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("document_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("reduction_level", sa.Integer(), server_default="0", nullable=False),
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
            "status in ('pending', 'running', 'completed', 'failed', 'not_ready')",
            name=op.f(
                "ck_knowledge_base_community_summaries_community_summary_status_valid"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f(
                "fk_knowledge_base_community_summaries_knowledge_base_id_knowledge_bases"
            ),
        ),
        sa.PrimaryKeyConstraint(
            "id", name=op.f("pk_knowledge_base_community_summaries")
        ),
        sa.UniqueConstraint(
            "knowledge_base_id",
            name="uq_knowledge_base_community_summaries_knowledge_base_id",
        ),
    )
    op.create_table(
        "document_summary_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_summary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parse_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vector", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("vector_size", sa.Integer(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column("summary_hash", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["document_summary_id"],
            ["document_summaries.id"],
            name=op.f(
                "fk_document_summary_embeddings_document_summary_id_document_summaries"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_document_summary_embeddings_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f(
                "fk_document_summary_embeddings_knowledge_base_id_knowledge_bases"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["parse_job_id"],
            ["parse_jobs.id"],
            name=op.f("fk_document_summary_embeddings_parse_job_id_parse_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_summary_embeddings")),
        sa.UniqueConstraint(
            "document_summary_id",
            name="uq_document_summary_embeddings_document_summary_id",
        ),
    )
    op.create_index(
        "idx_document_summary_embeddings_file",
        "document_summary_embeddings",
        ["file_id"],
    )
    op.create_table(
        "document_summary_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_summary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_document_summary_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("cross_knowledge_base", sa.Boolean(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "similarity >= 0 and similarity <= 1",
            name=op.f(
                "ck_document_summary_relations_document_summary_relation_similarity_valid"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["source_document_summary_id"],
            ["document_summaries.id"],
            name=op.f(
                "fk_document_summary_relations_source_document_summary_id_document_summaries"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["files.id"],
            name=op.f("fk_document_summary_relations_source_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["source_knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f(
                "fk_document_summary_relations_source_knowledge_base_id_knowledge_bases"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["target_document_summary_id"],
            ["document_summaries.id"],
            name=op.f(
                "fk_document_summary_relations_target_document_summary_id_document_summaries"
            ),
        ),
        sa.ForeignKeyConstraint(
            ["target_file_id"],
            ["files.id"],
            name=op.f("fk_document_summary_relations_target_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["target_knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f(
                "fk_document_summary_relations_target_knowledge_base_id_knowledge_bases"
            ),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_summary_relations")),
        sa.UniqueConstraint(
            "source_document_summary_id",
            "target_document_summary_id",
            name="uq_document_summary_relations_pair",
        ),
    )
    op.create_index(
        "idx_document_summary_relations_source_file",
        "document_summary_relations",
        ["source_file_id"],
    )
    op.create_index(
        "idx_document_summary_relations_target_file",
        "document_summary_relations",
        ["target_file_id"],
    )
    op.create_index(
        "idx_document_summary_relations_kb_pair",
        "document_summary_relations",
        ["source_knowledge_base_id", "target_knowledge_base_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_document_summary_relations_kb_pair",
        table_name="document_summary_relations",
    )
    op.drop_index(
        "idx_document_summary_relations_target_file",
        table_name="document_summary_relations",
    )
    op.drop_index(
        "idx_document_summary_relations_source_file",
        table_name="document_summary_relations",
    )
    op.drop_table("document_summary_relations")
    op.drop_index(
        "idx_document_summary_embeddings_file",
        table_name="document_summary_embeddings",
    )
    op.drop_table("document_summary_embeddings")
    op.drop_table("knowledge_base_community_summaries")
    op.drop_table("knowledge_graph_state")
