"""Create chunk-level knowledge graph tables.

Revision ID: 0017_chunk_knowledge_graph
Revises: 0016_community_per_doc
Create Date: 2026-06-30 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0017_chunk_knowledge_graph"
down_revision: str | None = "0016_community_per_doc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunk_summary_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            ["chunk_id"],
            ["chunks_metadata.id"],
            name=op.f("fk_chunk_summary_embeddings_chunk_id_chunks_metadata"),
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name=op.f("fk_chunk_summary_embeddings_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_chunk_summary_embeddings_knowledge_base_id_knowledge_bases"),
        ),
        sa.ForeignKeyConstraint(
            ["parse_job_id"],
            ["parse_jobs.id"],
            name=op.f("fk_chunk_summary_embeddings_parse_job_id_parse_jobs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk_summary_embeddings")),
        sa.UniqueConstraint(
            "chunk_id",
            name="uq_chunk_summary_embeddings_chunk_id",
        ),
    )
    op.create_index(
        "idx_chunk_summary_embeddings_kb",
        "chunk_summary_embeddings",
        ["knowledge_base_id"],
    )
    op.create_table(
        "chunk_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_chunk_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_file_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("knowledge_base_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("embedding_model", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "similarity >= 0 and similarity <= 1",
            name=op.f("ck_chunk_relations_chunk_relation_similarity_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["source_chunk_id"],
            ["chunks_metadata.id"],
            name=op.f("fk_chunk_relations_source_chunk_id_chunks_metadata"),
        ),
        sa.ForeignKeyConstraint(
            ["target_chunk_id"],
            ["chunks_metadata.id"],
            name=op.f("fk_chunk_relations_target_chunk_id_chunks_metadata"),
        ),
        sa.ForeignKeyConstraint(
            ["source_file_id"],
            ["files.id"],
            name=op.f("fk_chunk_relations_source_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["target_file_id"],
            ["files.id"],
            name=op.f("fk_chunk_relations_target_file_id_files"),
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            name=op.f("fk_chunk_relations_knowledge_base_id_knowledge_bases"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunk_relations")),
        sa.UniqueConstraint(
            "source_chunk_id",
            "target_chunk_id",
            name="uq_chunk_relations_pair",
        ),
    )
    op.create_index(
        "idx_chunk_relations_source",
        "chunk_relations",
        ["source_chunk_id"],
    )
    op.create_index(
        "idx_chunk_relations_target",
        "chunk_relations",
        ["target_chunk_id"],
    )
    op.create_index(
        "idx_chunk_relations_kb",
        "chunk_relations",
        ["knowledge_base_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_chunk_relations_kb", table_name="chunk_relations")
    op.drop_index("idx_chunk_relations_target", table_name="chunk_relations")
    op.drop_index("idx_chunk_relations_source", table_name="chunk_relations")
    op.drop_table("chunk_relations")
    op.drop_index(
        "idx_chunk_summary_embeddings_kb", table_name="chunk_summary_embeddings"
    )
    op.drop_table("chunk_summary_embeddings")
