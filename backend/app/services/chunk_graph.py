import hashlib
import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    ChunkKnowledgeExtraction,
    ChunkMetadata,
    ChunkRelation,
    ChunkSummaryEmbedding,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))

logger = logging.getLogger(__name__)


class EmbeddingClientProtocol(Protocol):
    model: str

    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class ChunkGraphItem:
    chunk_id: UUID
    file_id: UUID
    parse_job_id: UUID
    knowledge_base_id: UUID
    short_summary: str
    summary_hash: str


@dataclass(frozen=True)
class ChunkRelationDraft:
    source_chunk_id: UUID
    target_chunk_id: UUID
    source_file_id: UUID
    target_file_id: UUID
    knowledge_base_id: UUID
    similarity: float


def load_chunk_graph_items(
    db: Session,
    *,
    knowledge_base_id: UUID | None = None,
) -> list[ChunkGraphItem]:
    query = (
        select(ChunkKnowledgeExtraction, ChunkMetadata)
        .join(ChunkMetadata, ChunkMetadata.id == ChunkKnowledgeExtraction.chunk_id)
        .join(File, File.id == ChunkMetadata.file_id)
        .join(
            KnowledgeBase,
            KnowledgeBase.id == ChunkMetadata.knowledge_base_id,
        )
        .where(
            ChunkKnowledgeExtraction.status == "completed",
            ChunkKnowledgeExtraction.short_summary.is_not(None),
            ChunkKnowledgeExtraction.short_summary != "",
            ChunkMetadata.is_active.is_(True),
            File.deleted_at.is_(None),
            File.status == FileStatus.INDEXED.value,
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        )
        .order_by(
            ChunkMetadata.knowledge_base_id,
            ChunkMetadata.file_id,
            ChunkMetadata.chunk_index,
        )
    )
    if knowledge_base_id is not None:
        query = query.where(ChunkMetadata.knowledge_base_id == knowledge_base_id)
    rows = db.execute(query).all()
    items: list[ChunkGraphItem] = []
    for extraction, chunk in rows:
        summary_text = extraction.short_summary or ""
        items.append(
            ChunkGraphItem(
                chunk_id=extraction.chunk_id,
                file_id=chunk.file_id,
                parse_job_id=chunk.parse_job_id,
                knowledge_base_id=chunk.knowledge_base_id,
                short_summary=summary_text,
                summary_hash=hashlib.sha256(
                    summary_text.encode("utf-8")
                ).hexdigest(),
            )
        )
    return items


def load_chunk_embedding_cache(
    session_factory: sessionmaker[Session],
    *,
    chunk_ids: list[UUID],
) -> dict[UUID, ChunkSummaryEmbedding]:
    if not chunk_ids:
        return {}
    with session_factory() as db:
        return {
            row.chunk_id: row
            for row in db.scalars(
                select(ChunkSummaryEmbedding).where(
                    ChunkSummaryEmbedding.chunk_id.in_(chunk_ids)
                )
            ).all()
        }


def save_chunk_embedding_batch(
    session_factory: sessionmaker[Session],
    *,
    items: list[ChunkGraphItem],
    vectors: list[list[float]],
    embedding_model: str,
) -> None:
    with session_factory() as db:
        existing = {
            row.chunk_id: row
            for row in db.scalars(
                select(ChunkSummaryEmbedding).where(
                    ChunkSummaryEmbedding.chunk_id.in_(
                        [item.chunk_id for item in items]
                    )
                )
            ).all()
        }
        for item, vector in zip(items, vectors, strict=True):
            row = existing.get(item.chunk_id)
            if row is None:
                row = ChunkSummaryEmbedding(
                    chunk_id=item.chunk_id,
                    file_id=item.file_id,
                    knowledge_base_id=item.knowledge_base_id,
                    parse_job_id=item.parse_job_id,
                    vector=vector,
                    vector_size=len(vector),
                    embedding_model=embedding_model,
                    summary_hash=item.summary_hash,
                )
                db.add(row)
            else:
                row.vector = vector
                row.vector_size = len(vector)
                row.embedding_model = embedding_model
                row.summary_hash = item.summary_hash
        db.commit()


def ensure_chunk_summary_embeddings(
    session_factory: sessionmaker[Session],
    *,
    items: list[ChunkGraphItem],
    embedding_client: EmbeddingClientProtocol,
    batch_size: int,
) -> dict[UUID, list[float]]:
    cached = load_chunk_embedding_cache(
        session_factory,
        chunk_ids=[item.chunk_id for item in items],
    )
    stale = [
        item
        for item in items
        if (
            item.chunk_id not in cached
            or cached[item.chunk_id].summary_hash != item.summary_hash
            or cached[item.chunk_id].embedding_model != embedding_client.model
        )
    ]
    if stale:
        for start in range(0, len(stale), batch_size):
            batch = stale[start : start + batch_size]
            vectors = embedding_client.embed_texts(
                [item.short_summary for item in batch]
            )
            if len(vectors) != len(batch):
                logger.error(
                    "Chunk embedding count mismatch: expected %d, got %d",
                    len(batch),
                    len(vectors),
                )
                continue
            save_chunk_embedding_batch(
                session_factory,
                items=batch,
                vectors=vectors,
                embedding_model=embedding_client.model,
            )
    refreshed = load_chunk_embedding_cache(
        session_factory,
        chunk_ids=[item.chunk_id for item in items],
    )
    return {
        chunk_id: [float(value) for value in row.vector]
        for chunk_id, row in refreshed.items()
    }


def calculate_chunk_relation_drafts(
    items: list[ChunkGraphItem],
    vectors: dict[UUID, list[float]],
    *,
    threshold: float,
    max_relations_per_chunk: int,
) -> list[ChunkRelationDraft]:
    ranked: dict[UUID, list[tuple[float, ChunkGraphItem]]] = defaultdict(list)
    items_by_id = {item.chunk_id: item for item in items}
    for index, left in enumerate(items):
        left_vector = vectors.get(left.chunk_id)
        if left_vector is None:
            continue
        for right in items[index + 1 :]:
            if left.knowledge_base_id != right.knowledge_base_id:
                continue
            right_vector = vectors.get(right.chunk_id)
            if right_vector is None:
                continue
            similarity = cosine_similarity(left_vector, right_vector)
            if similarity < threshold:
                continue
            ranked[left.chunk_id].append((similarity, right))
            ranked[right.chunk_id].append((similarity, left))

    selected_pairs: dict[tuple[UUID, UUID], float] = {}
    for chunk_id, candidates in ranked.items():
        for similarity, related in sorted(
            candidates,
            key=lambda item: (-item[0], str(item[1].chunk_id)),
        )[:max_relations_per_chunk]:
            pair = tuple(sorted((chunk_id, related.chunk_id), key=str))
            selected_pairs[pair] = max(selected_pairs.get(pair, 0.0), similarity)

    drafts: list[ChunkRelationDraft] = []
    for (source_id, target_id), similarity in sorted(
        selected_pairs.items(),
        key=lambda item: (-item[1], str(item[0][0]), str(item[0][1])),
    ):
        source = items_by_id[source_id]
        target = items_by_id[target_id]
        drafts.append(
            ChunkRelationDraft(
                source_chunk_id=source_id,
                target_chunk_id=target_id,
                source_file_id=source.file_id,
                target_file_id=target.file_id,
                knowledge_base_id=source.knowledge_base_id,
                similarity=similarity,
            )
        )
    return drafts


def replace_chunk_relations(
    session_factory: sessionmaker[Session],
    *,
    knowledge_base_id: UUID,
    drafts: list[ChunkRelationDraft],
    embedding_model: str,
) -> None:
    with session_factory() as db:
        db.execute(
            delete(ChunkRelation).where(
                ChunkRelation.knowledge_base_id == knowledge_base_id
            )
        )
        db.add_all(
            [
                ChunkRelation(
                    source_chunk_id=draft.source_chunk_id,
                    target_chunk_id=draft.target_chunk_id,
                    source_file_id=draft.source_file_id,
                    target_file_id=draft.target_file_id,
                    knowledge_base_id=draft.knowledge_base_id,
                    similarity=draft.similarity,
                    embedding_model=embedding_model,
                )
                for draft in drafts
            ]
        )
        db.commit()


def build_chunk_graph_for_knowledge_base(
    session_factory: sessionmaker[Session],
    *,
    knowledge_base_id: UUID,
    embedding_client: EmbeddingClientProtocol,
    batch_size: int,
    threshold: float,
    max_relations_per_chunk: int,
) -> int:
    with session_factory() as db:
        items = load_chunk_graph_items(db, knowledge_base_id=knowledge_base_id)
    if not items:
        logger.info(
            "No chunk graph items found for knowledge_base_id=%s", knowledge_base_id
        )
        return 0
    vectors = ensure_chunk_summary_embeddings(
        session_factory,
        items=items,
        embedding_client=embedding_client,
        batch_size=batch_size,
    )
    drafts = calculate_chunk_relation_drafts(
        items,
        vectors,
        threshold=threshold,
        max_relations_per_chunk=max_relations_per_chunk,
    )
    replace_chunk_relations(
        session_factory,
        knowledge_base_id=knowledge_base_id,
        drafts=drafts,
        embedding_model=embedding_client.model,
    )
    logger.info(
        "Chunk graph built for knowledge_base_id=%s: %d items, %d relations",
        knowledge_base_id,
        len(items),
        len(drafts),
    )
    return len(drafts)
