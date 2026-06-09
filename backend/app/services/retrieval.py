from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, literal, or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import ChunkMetadata, File, FileStatus, KnowledgeBase, KnowledgeBaseStatus
from app.schemas.retrieval import (
    RetrievalResultItem,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from app.services.content_normalization import normalize_special_elements
from app.services.bm25_index import BM25IndexClientProtocol
from app.services.chunk_text import build_display_chunk_text, build_indexable_chunk_text
from app.services.embedding import EmbeddingClientProtocol
from app.services.reranker import RerankerClientProtocol
from app.services.vector_index import VectorIndexClientProtocol, VectorSearchHit
from app.services.visual_citations import (
    build_chunk_image_alt,
    build_chunk_image_url,
    build_chunk_image_urls,
    infer_chunk_modality,
)


@dataclass
class RetrievalCandidate:
    chunk_id: UUID
    score: float
    source: str


RRF_K = 60
RERANK_CANDIDATE_LIMIT = 20


def search_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: UUID,
    payload: RetrievalSearchRequest,
    embedding_client: EmbeddingClientProtocol,
    reranker_client: RerankerClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
) -> RetrievalSearchResponse:
    require_active_knowledge_base(db, knowledge_base_id)
    query = payload.query.strip()
    if not query:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Query cannot be empty.",
            status_code=422,
        )

    if not has_searchable_chunks(db, knowledge_base_id=knowledge_base_id):
        return RetrievalSearchResponse(
            knowledge_base_id=str(knowledge_base_id),
            query=query,
            items=[],
            total=0,
        )

    vector_candidates = search_vector_candidates(
        query=query,
        knowledge_base_id=knowledge_base_id,
        limit=payload.vector_top_k,
        embedding_client=embedding_client,
        vector_index_client=vector_index_client,
    )
    full_text_candidates = search_keyword_candidates(
        db,
        query=query,
        knowledge_base_id=knowledge_base_id,
        limit=payload.full_text_top_k,
        bm25_index_client=bm25_index_client,
    )
    merged_candidates = merge_candidates(vector_candidates, full_text_candidates)
    rerank_input_candidates = merged_candidates[:RERANK_CANDIDATE_LIMIT]
    chunks_by_id = load_chunks(
        db,
        chunk_ids=[candidate.chunk_id for candidate in rerank_input_candidates],
        knowledge_base_id=knowledge_base_id,
    )
    reranked_candidates = rerank_candidates(
        query=query,
        candidates=rerank_input_candidates,
        chunks_by_id=chunks_by_id,
        reranker_client=reranker_client,
    )
    limited_candidates = reranked_candidates[: payload.top_k]

    items: list[RetrievalResultItem] = []
    for candidate in limited_candidates:
        chunk_and_file = chunks_by_id.get(candidate.chunk_id)
        if chunk_and_file is None:
            continue
        chunk, file = chunk_and_file
        items.append(
            RetrievalResultItem(
                chunk_id=str(chunk.id),
                file_id=str(file.id),
                file_name=file.file_name,
                source_locator=chunk.source_locator,
                excerpt=build_excerpt(build_display_chunk_text(chunk)),
                score=candidate.score,
                source=candidate.source,
                modality=infer_chunk_modality(chunk),
                image_url=build_chunk_image_url(chunk),
                image_urls=build_chunk_image_urls(chunk),
                image_alt=build_chunk_image_alt(chunk, file),
            )
        )

    return RetrievalSearchResponse(
        knowledge_base_id=str(knowledge_base_id),
        query=query,
        items=items,
        total=len(items),
    )


def rerank_candidates(
    *,
    query: str,
    candidates: list[RetrievalCandidate],
    chunks_by_id: dict[UUID, tuple[ChunkMetadata, File]],
    reranker_client: RerankerClientProtocol,
) -> list[RetrievalCandidate]:
    candidates_with_chunks = [
        candidate for candidate in candidates if candidate.chunk_id in chunks_by_id
    ]
    if not candidates_with_chunks:
        return []
    documents = [
        build_indexable_chunk_text(chunks_by_id[candidate.chunk_id][0])
        for candidate in candidates_with_chunks
    ]
    scores = reranker_client.rerank(query=query, documents=documents)
    reranked: list[RetrievalCandidate] = []
    for candidate, score in zip(candidates_with_chunks, scores, strict=True):
        reranked.append(
            RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                score=score,
                source=candidate.source,
            )
        )
    return sorted(reranked, key=lambda item: item.score, reverse=True)


def has_searchable_chunks(db: Session, *, knowledge_base_id: UUID) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(ChunkMetadata)
        .join(File, File.id == ChunkMetadata.file_id)
        .where(
            ChunkMetadata.knowledge_base_id == knowledge_base_id,
            ChunkMetadata.is_active.is_(True),
            File.deleted_at.is_(None),
            File.status == FileStatus.INDEXED.value,
        )
    )
    return bool(count)


def search_vector_candidates(
    *,
    query: str,
    knowledge_base_id: UUID,
    limit: int,
    embedding_client: EmbeddingClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
) -> list[RetrievalCandidate]:
    vectors = embedding_client.embed_texts([query])
    if not vectors:
        return []
    hits = vector_index_client.search_points(
        vector=vectors[0],
        knowledge_base_id=str(knowledge_base_id),
        limit=limit,
    )
    return [build_vector_candidate(hit) for hit in hits if extract_chunk_id(hit) is not None]


def build_vector_candidate(hit: VectorSearchHit) -> RetrievalCandidate:
    chunk_id = extract_chunk_id(hit)
    if chunk_id is None:
        raise ApiError(
            code="UPSTREAM_SERVICE_ERROR",
            message="Qdrant search hit did not include a valid chunk_id.",
            status_code=502,
            details={"point_id": hit.point_id},
        )
    return RetrievalCandidate(chunk_id=chunk_id, score=hit.score, source="vector")


def extract_chunk_id(hit: VectorSearchHit) -> UUID | None:
    raw_chunk_id = hit.payload.get("chunk_id") or hit.point_id
    try:
        return UUID(str(raw_chunk_id))
    except ValueError:
        return None


def search_keyword_candidates(
    db: Session,
    *,
    query: str,
    knowledge_base_id: UUID,
    limit: int,
    bm25_index_client: BM25IndexClientProtocol,
) -> list[RetrievalCandidate]:
    if bm25_index_client.enabled:
        return search_bm25_candidates(
            query=query,
            knowledge_base_id=knowledge_base_id,
            limit=limit,
            bm25_index_client=bm25_index_client,
        )
    return search_full_text_candidates(
        db,
        query=query,
        knowledge_base_id=knowledge_base_id,
        limit=limit,
    )


def search_bm25_candidates(
    *,
    query: str,
    knowledge_base_id: UUID,
    limit: int,
    bm25_index_client: BM25IndexClientProtocol,
) -> list[RetrievalCandidate]:
    hits = bm25_index_client.search(
        query=query,
        knowledge_base_id=str(knowledge_base_id),
        limit=limit,
    )
    candidates: list[RetrievalCandidate] = []
    for hit in hits:
        try:
            chunk_id = UUID(hit.chunk_id)
        except ValueError:
            continue
        candidates.append(
            RetrievalCandidate(chunk_id=chunk_id, score=hit.score, source="full_text")
        )
    return candidates


def search_full_text_candidates(
    db: Session,
    *,
    query: str,
    knowledge_base_id: UUID,
    limit: int,
) -> list[RetrievalCandidate]:
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        return search_postgres_full_text(
            db,
            query=query,
            knowledge_base_id=knowledge_base_id,
            limit=limit,
        )
    return search_sqlite_full_text(
        db,
        query=query,
        knowledge_base_id=knowledge_base_id,
        limit=limit,
    )


def search_postgres_full_text(
    db: Session,
    *,
    query: str,
    knowledge_base_id: UUID,
    limit: int,
) -> list[RetrievalCandidate]:
    ts_query = func.websearch_to_tsquery("simple", query)
    rank = func.ts_rank(ChunkMetadata.tsv, ts_query)
    rows = db.execute(
        select(ChunkMetadata.id, rank)
        .join(File, File.id == ChunkMetadata.file_id)
        .where(
            ChunkMetadata.knowledge_base_id == knowledge_base_id,
            ChunkMetadata.is_active.is_(True),
            ChunkMetadata.tsv.op("@@")(ts_query),
            File.deleted_at.is_(None),
            File.status == FileStatus.INDEXED.value,
        )
        .order_by(rank.desc())
        .limit(limit)
    ).all()
    return [
        RetrievalCandidate(chunk_id=row[0], score=float(row[1] or 0.0), source="full_text")
        for row in rows
    ]


def search_sqlite_full_text(
    db: Session,
    *,
    query: str,
    knowledge_base_id: UUID,
    limit: int,
) -> list[RetrievalCandidate]:
    words = [word.strip() for word in query.split() if word.strip()]
    content_filters = [ChunkMetadata.content.ilike(f"%{word}%") for word in words] or [
        ChunkMetadata.content.ilike(f"%{query}%")
    ]
    description_filters = [ChunkMetadata.description.ilike(f"%{word}%") for word in words] or [
        ChunkMetadata.description.ilike(f"%{query}%")
    ]
    rows = db.execute(
        select(ChunkMetadata.id, literal(1.0))
        .join(File, File.id == ChunkMetadata.file_id)
        .where(
            ChunkMetadata.knowledge_base_id == knowledge_base_id,
            ChunkMetadata.is_active.is_(True),
            or_(*content_filters, *description_filters),
            File.deleted_at.is_(None),
            File.status == FileStatus.INDEXED.value,
        )
        .order_by(ChunkMetadata.chunk_index)
        .limit(limit)
    ).all()
    return [
        RetrievalCandidate(chunk_id=row[0], score=float(row[1] or 0.0), source="full_text")
        for row in rows
    ]


def merge_candidates(
    vector_candidates: list[RetrievalCandidate],
    full_text_candidates: list[RetrievalCandidate],
    *,
    rrf_k: int = RRF_K,
) -> list[RetrievalCandidate]:
    merged: dict[UUID, RetrievalCandidate] = {}
    for source_candidates in (vector_candidates, full_text_candidates):
        for rank, candidate in enumerate(source_candidates, start=1):
            existing = merged.get(candidate.chunk_id)
            source = candidate.source
            score = 1.0 / (rrf_k + rank)
            if existing is not None:
                source = "hybrid" if existing.source != candidate.source else existing.source
                score += existing.score
            merged[candidate.chunk_id] = RetrievalCandidate(
                chunk_id=candidate.chunk_id,
                score=score,
                source=source,
            )
    return sorted(merged.values(), key=lambda item: item.score, reverse=True)


def load_chunks(
    db: Session, *, chunk_ids: list[UUID], knowledge_base_id: UUID
) -> dict[UUID, tuple[ChunkMetadata, File]]:
    if not chunk_ids:
        return {}
    rows = db.execute(
        select(ChunkMetadata, File)
        .join(File, File.id == ChunkMetadata.file_id)
        .where(
            ChunkMetadata.id.in_(chunk_ids),
            ChunkMetadata.knowledge_base_id == knowledge_base_id,
            ChunkMetadata.is_active.is_(True),
            File.deleted_at.is_(None),
            File.status == FileStatus.INDEXED.value,
        )
    ).all()
    return {row[0].id: (row[0], row[1]) for row in rows}


def build_excerpt(content: str, *, max_length: int = 300) -> str:
    normalized = " ".join(normalize_special_elements(content).split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


def require_active_knowledge_base(db: Session, knowledge_base_id: UUID) -> KnowledgeBase:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if (
        knowledge_base is None
        or knowledge_base.deleted_at is not None
        or knowledge_base.status != KnowledgeBaseStatus.ACTIVE.value
    ):
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Knowledge base was not found.",
            status_code=404,
        )
    return knowledge_base
