import argparse
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import KnowledgeBase, KnowledgeBaseStatus
from app.services.chunk_graph import build_chunk_graph_for_knowledge_base
from app.services.embedding import get_embedding_client


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build chunk-level knowledge graph for active knowledge bases."
    )
    parser.add_argument("--knowledge-base-id", type=UUID)
    args = parser.parse_args()

    settings = get_settings()
    embedding_client = get_embedding_client()

    with SessionLocal() as db:
        query = select(KnowledgeBase).where(
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        )
        if args.knowledge_base_id:
            query = query.where(KnowledgeBase.id == args.knowledge_base_id)
        knowledge_bases = list(db.scalars(query).all())

    total_relations = 0
    for kb in knowledge_bases:
        relations = build_chunk_graph_for_knowledge_base(
            SessionLocal,
            knowledge_base_id=kb.id,
            embedding_client=embedding_client,
            batch_size=settings.chunk_graph_embedding_batch_size,
            threshold=settings.chunk_graph_similarity_threshold,
            max_relations_per_chunk=settings.chunk_graph_max_relations_per_chunk,
        )
        total_relations += relations
        print(f"  {kb.name} ({kb.id}): {relations} relations")

    print(
        f"chunk graph backfill: knowledge_bases={len(knowledge_bases)} "
        f"total_relations={total_relations}"
    )


if __name__ == "__main__":
    main()
