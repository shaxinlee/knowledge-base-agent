from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import ChunkMetadata, File, FileStatus, ParseJob, ParseJobStatus
from app.services.bm25_index import BM25ChunkDocument, BM25IndexClientProtocol
from app.services.chunk_text import build_indexable_chunk_text
from app.services.embedding import EmbeddingClientProtocol
from app.services.visual_citations import get_asset_paths, infer_chunk_modality
from app.services.vector_index import VectorIndexClientProtocol


def index_parse_job(
    db: Session,
    *,
    file: File,
    parse_job: ParseJob,
    embedding_client: EmbeddingClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
) -> None:
    chunks = db.scalars(
        select(ChunkMetadata)
        .where(
            ChunkMetadata.parse_job_id == parse_job.id,
            ChunkMetadata.file_id == file.id,
            ChunkMetadata.is_active.is_(True),
        )
        .order_by(ChunkMetadata.chunk_index)
    ).all()
    if not chunks:
        mark_indexing_failed(
            db,
            file=file,
            parse_job=parse_job,
            error_code="NO_ACTIVE_CHUNKS",
            error_message="No active chunks were found for indexing.",
        )
        return

    parse_job.status = ParseJobStatus.INDEXING.value
    parse_job.progress = 75
    parse_job.logs = merge_indexing_logs(
        parse_job.logs,
        {
            "indexing": {
                "chunk_count": len(chunks),
                "embedding_model": embedding_client.model,
                "qdrant_collection": vector_index_client.collection_name,
            }
        },
    )
    db.commit()

    try:
        vectors = embed_texts_in_batches(
            embedding_client,
            [build_indexable_chunk_text(chunk) for chunk in chunks],
        )
        validate_vectors(vectors=vectors, expected_count=len(chunks))
        vector_size = len(vectors[0])
        vector_index_client.ensure_collection(vector_size=vector_size)
        bm25_index_client.ensure_index()
        points = []
        bm25_documents = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            indexable_text = build_indexable_chunk_text(chunk)
            write_chunk_tsv(db, chunk=chunk, content=indexable_text)
            points.append(
                build_qdrant_point(file=file, parse_job=parse_job, chunk=chunk, vector=vector)
            )
            bm25_documents.append(build_bm25_document(file=file, parse_job=parse_job, chunk=chunk))
        vector_index_client.upsert_points(points=points)
        bm25_index_client.upsert_chunks(documents=bm25_documents)
    except ApiError as exc:
        mark_indexing_failed(
            db,
            file=file,
            parse_job=parse_job,
            error_code=exc.code,
            error_message=exc.message,
            details=exc.details,
        )
        return
    except Exception as exc:
        mark_indexing_failed(
            db,
            file=file,
            parse_job=parse_job,
            error_code="INDEXING_FAILED",
            error_message=str(exc),
        )
        return

    parse_job.status = ParseJobStatus.INDEXED.value
    parse_job.progress = 100
    parse_job.error_code = None
    parse_job.error_message = None
    parse_job.finished_at = datetime.now(UTC)
    parse_job.logs = merge_indexing_logs(
        clear_indexing_error_log(parse_job.logs),
        {
            "indexing": {
                "chunk_count": len(chunks),
                "embedding_model": embedding_client.model,
                "qdrant_collection": vector_index_client.collection_name,
                "bm25_provider": bm25_index_client.provider,
                "bm25_index": bm25_index_client.index_name,
                "vector_size": len(vectors[0]),
                "status": "indexed",
            }
        },
    )
    file.status = FileStatus.INDEXED.value
    db.commit()


def validate_vectors(*, vectors: list[list[float]], expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise ApiError(
            code="EMBEDDING_VECTOR_COUNT_MISMATCH",
            message="Embedding vector count does not match chunk count.",
            status_code=502,
            details={"expected": expected_count, "actual": len(vectors)},
        )
    vector_size = len(vectors[0]) if vectors else 0
    if vector_size <= 0:
        raise ApiError(
            code="EMBEDDING_VECTOR_INVALID",
            message="Embedding service returned empty vectors.",
            status_code=502,
            details={},
        )
    if any(len(vector) != vector_size for vector in vectors):
        raise ApiError(
            code="EMBEDDING_VECTOR_DIMENSION_MISMATCH",
            message="Embedding service returned vectors with inconsistent dimensions.",
            status_code=502,
            details={"vector_size": vector_size},
        )


def embed_texts_in_batches(
    embedding_client: EmbeddingClientProtocol,
    texts: list[str],
    *,
    batch_size: int | None = None,
) -> list[list[float]]:
    normalized_batch_size = max(batch_size or get_settings().embedding_batch_size, 1)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), normalized_batch_size):
        batch = texts[start : start + normalized_batch_size]
        vectors.extend(embedding_client.embed_texts(batch))
    return vectors


def write_chunk_tsv(db: Session, *, chunk: ChunkMetadata, content: str | None = None) -> None:
    indexable_text = content if content is not None else build_indexable_chunk_text(chunk)
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        db.execute(
            update(ChunkMetadata)
            .where(ChunkMetadata.id == chunk.id)
            .values(tsv=func.to_tsvector("simple", indexable_text))
        )
    else:
        chunk.tsv = indexable_text


def build_qdrant_point(
    *,
    file: File,
    parse_job: ParseJob,
    chunk: ChunkMetadata,
    vector: list[float],
) -> dict[str, Any]:
    return {
        "id": str(chunk.id),
        "vector": vector,
        "payload": {
            "chunk_id": str(chunk.id),
            "knowledge_base_id": str(chunk.knowledge_base_id),
            "file_id": str(chunk.file_id),
            "parse_job_id": str(parse_job.id),
            "file_name": file.file_name,
            "source_type": chunk.source_type,
            "source_locator": chunk.source_locator,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "slide_number": chunk.slide_number,
            "sheet_name": chunk.sheet_name,
            "row_start": chunk.row_start,
            "row_end": chunk.row_end,
            "heading_path": chunk.heading_path,
            "description": chunk.description,
            "asset_paths": get_asset_paths(chunk),
            "modality": infer_chunk_modality(chunk),
            "is_active": chunk.is_active,
            "token_count": chunk.token_count,
            "content_hash": chunk.content_hash,
        },
    }


def build_bm25_document(
    *,
    file: File,
    parse_job: ParseJob,
    chunk: ChunkMetadata,
) -> BM25ChunkDocument:
    return BM25ChunkDocument(
        chunk_id=str(chunk.id),
        knowledge_base_id=str(chunk.knowledge_base_id),
        file_id=str(chunk.file_id),
        parse_job_id=str(parse_job.id),
        file_name=file.file_name,
        content=build_indexable_chunk_text(chunk),
        source_locator=chunk.source_locator,
        source_type=chunk.source_type,
        heading_path=chunk.heading_path,
        is_active=chunk.is_active,
        created_at=chunk.created_at,
    )


def mark_indexing_failed(
    db: Session,
    *,
    file: File,
    parse_job: ParseJob,
    error_code: str,
    error_message: str,
    details: dict[str, Any] | None = None,
) -> None:
    parse_job.status = ParseJobStatus.FAILED.value
    parse_job.error_code = error_code
    parse_job.error_message = error_message
    parse_job.logs = merge_indexing_logs(
        parse_job.logs,
        {
            "indexing_error": {
                "code": error_code,
                "message": error_message,
                "details": details or {},
            }
        },
    )
    file.status = FileStatus.FAILED.value
    db.commit()


def merge_indexing_logs(
    existing_logs: dict[str, Any] | None, new_logs: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(existing_logs or {})
    merged.update(new_logs)
    return merged


def clear_indexing_error_log(existing_logs: dict[str, Any] | None) -> dict[str, Any]:
    logs = dict(existing_logs or {})
    logs.pop("indexing_error", None)
    return logs
