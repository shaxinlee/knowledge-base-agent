from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File as FormFile,
    Form,
    Query,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user, require_admin_user
from app.db.session import get_db, get_session_factory
from app.models import FileStatus, User
from app.schemas.files import (
    ChunkDebugListResponse,
    FileListResponse,
    FileResponse,
    FileStatusResponse,
    FileUploadResponse,
    ParseJobResponse,
)
from app.schemas.document_summaries import (
    DocumentSummaryResponse,
    DocumentSummaryRetryRequest,
)
from app.services.files import (
    delete_file,
    get_file,
    get_file_status,
    list_file_debug_chunks,
    list_files,
    retry_parse_file,
    upload_files,
)
from app.services.document_summaries import (
    get_document_summary_response,
    retry_document_summary,
)
from app.services.file_assets import get_parsed_file_asset, get_raw_file_asset
from app.services.parse_pipeline import run_parse_job_background
from app.services.bm25_index import BM25IndexClientProtocol, get_bm25_index_client
from app.services.embedding import EmbeddingClientProtocol, get_embedding_client
from app.services.image_descriptions import (
    ImageDescriptionClientProtocol,
    get_image_description_client,
)
from app.services.mineru import MineruClient, get_mineru_client
from app.services.object_storage import ObjectStorage, get_object_storage
from app.services.vector_index import VectorIndexClientProtocol, get_vector_index_client

router = APIRouter(tags=["Files"])

__all__ = [
    "get_embedding_client",
    "get_image_description_client",
    "get_bm25_index_client",
    "get_mineru_client",
    "get_object_storage",
    "get_vector_index_client",
    "router",
]


@router.get("/knowledge-bases/{knowledge_base_id}/files", response_model=FileListResponse)
def read_files(
    knowledge_base_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = None,
    status: FileStatus | None = None,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> FileListResponse:
    return list_files(
        db,
        knowledge_base_id=knowledge_base_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
    )


@router.post(
    "/knowledge-bases/{knowledge_base_id}/files/upload",
    response_model=FileUploadResponse,
    status_code=202,
)
async def upload_files_endpoint(
    knowledge_base_id: UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = FormFile(...),
    force: bool = Form(default=False),
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    admin: User = Depends(require_admin_user),
    storage: ObjectStorage = Depends(get_object_storage),
    mineru_client: MineruClient = Depends(get_mineru_client),
    embedding_client: EmbeddingClientProtocol = Depends(get_embedding_client),
    vector_index_client: VectorIndexClientProtocol = Depends(get_vector_index_client),
    bm25_index_client: BM25IndexClientProtocol = Depends(get_bm25_index_client),
    image_description_client: ImageDescriptionClientProtocol = Depends(
        get_image_description_client
    ),
) -> FileUploadResponse:
    response = await upload_files(
        db,
        knowledge_base_id=knowledge_base_id,
        uploads=files,
        force=force,
        actor=admin,
        storage=storage,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    for uploaded_item in response.uploaded:
        background_tasks.add_task(
            run_parse_job_background,
            session_factory=session_factory,
            parse_job_id=UUID(uploaded_item.parse_job.id),
            storage=storage,
            mineru_client=mineru_client,
            embedding_client=embedding_client,
            vector_index_client=vector_index_client,
            bm25_index_client=bm25_index_client,
            image_description_client=image_description_client,
        )
    return response


@router.get("/files/{file_id}", response_model=FileResponse)
def read_file(
    file_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> FileResponse:
    return get_file(db, file_id=file_id)


@router.get("/files/{file_id}/status", response_model=FileStatusResponse)
def read_file_status(
    file_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> FileStatusResponse:
    return get_file_status(db, file_id=file_id)


@router.get("/files/{file_id}/summary", response_model=DocumentSummaryResponse)
def read_file_summary(
    file_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> DocumentSummaryResponse:
    return get_document_summary_response(db, file_id=file_id)


@router.post(
    "/files/{file_id}/summary/retry",
    response_model=DocumentSummaryResponse,
    status_code=202,
)
def retry_file_summary(
    file_id: UUID,
    payload: DocumentSummaryRetryRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> DocumentSummaryResponse:
    return retry_document_summary(db, file_id=file_id, force=payload.force)


@router.get("/files/{file_id}/chunks", response_model=ChunkDebugListResponse)
def read_file_chunks(
    file_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> ChunkDebugListResponse:
    return list_file_debug_chunks(db, file_id=file_id, page=page, page_size=page_size)


@router.get("/files/{file_id}/raw", response_model=None)
def read_raw_file_asset(
    file_id: UUID,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    asset = get_raw_file_asset(db, file_id=file_id, storage=storage)
    return Response(content=asset.content, media_type=asset.media_type)


@router.get("/files/{file_id}/assets", response_model=None)
def read_parsed_file_asset(
    file_id: UUID,
    path: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    asset = get_parsed_file_asset(db, file_id=file_id, asset_path=path, storage=storage)
    return Response(content=asset.content, media_type=asset.media_type)


@router.post("/files/{file_id}/retry-parse", response_model=ParseJobResponse, status_code=202)
def retry_file_parse_endpoint(
    file_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    admin: User = Depends(require_admin_user),
    storage: ObjectStorage = Depends(get_object_storage),
    mineru_client: MineruClient = Depends(get_mineru_client),
    embedding_client: EmbeddingClientProtocol = Depends(get_embedding_client),
    vector_index_client: VectorIndexClientProtocol = Depends(get_vector_index_client),
    bm25_index_client: BM25IndexClientProtocol = Depends(get_bm25_index_client),
    image_description_client: ImageDescriptionClientProtocol = Depends(
        get_image_description_client
    ),
) -> ParseJobResponse:
    response = retry_parse_file(
        db,
        file_id=file_id,
        actor=admin,
    )
    background_tasks.add_task(
        run_parse_job_background,
        session_factory=session_factory,
        parse_job_id=UUID(response.id),
        storage=storage,
        mineru_client=mineru_client,
        embedding_client=embedding_client,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
        image_description_client=image_description_client,
    )
    return response


@router.delete("/files/{file_id}", status_code=204)
def delete_file_endpoint(
    file_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
    vector_index_client: VectorIndexClientProtocol = Depends(get_vector_index_client),
    bm25_index_client: BM25IndexClientProtocol = Depends(get_bm25_index_client),
) -> Response:
    delete_file(
        db,
        file_id=file_id,
        actor=admin,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)


@router.post("/files/{file_id}/reindex", status_code=200)
def reindex_file_vectors(
    file_id: UUID,
    db: Session = Depends(get_db),
    session_factory: sessionmaker[Session] = Depends(get_session_factory),
    admin: User = Depends(require_admin_user),
    embedding_client: EmbeddingClientProtocol = Depends(get_embedding_client),
    vector_index_client: VectorIndexClientProtocol = Depends(get_vector_index_client),
    bm25_index_client: BM25IndexClientProtocol = Depends(get_bm25_index_client),
) -> dict:
    """Re-embed existing chunks and re-index into Qdrant + BM25 without re-parsing."""
    from app.services.indexing import index_parse_job, build_qdrant_point, embed_texts_in_batches
    from app.services.chunk_text import build_indexable_chunk_text
    from app.models import ChunkMetadata, ParseJob, ParseJobStatus
    from sqlalchemy import select

    file = get_file(db, file_id=file_id)

    # Get the latest parse job for this file
    parse_job = db.scalar(
        select(ParseJob).where(
            ParseJob.file_id == file_id,
        ).order_by(ParseJob.created_at.desc()).limit(1)
    )
    if parse_job is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="No active parse job found for this file")

    # Deactivate old Qdrant points for this file
    active_chunks = db.scalars(
        select(ChunkMetadata).where(
            ChunkMetadata.parse_job_id == parse_job.id,
            ChunkMetadata.is_active.is_(True),
        ).order_by(ChunkMetadata.chunk_index)
    ).all()

    if active_chunks:
        # Try to deactivate old points (skip if collection is empty/new)
        point_ids = [str(c.id) for c in active_chunks]
        try:
            vector_index_client.deactivate_points(point_ids=point_ids)
        except Exception:
            pass  # Collection may be empty/new, skip deactivation

        # Build indexable text and embed
        texts = [build_indexable_chunk_text(chunk) for chunk in active_chunks]
        vectors = embed_texts_in_batches(embedding_client, texts)

        # Build Qdrant points
        points = []
        for chunk, vector in zip(active_chunks, vectors, strict=True):
            points.append(build_qdrant_point(
                file=file, parse_job=parse_job, chunk=chunk, vector=vector
            ))

        # Upsert to Qdrant and BM25
        vector_index_client.upsert_points(points=points)

        # Rebuild BM25 documents
        from app.services.bm25_index import BM25ChunkDocument
        bm25_documents = []
        for chunk, text in zip(active_chunks, texts, strict=True):
            bm25_documents.append(BM25ChunkDocument(
                chunk_id=str(chunk.id),
                knowledge_base_id=str(file.knowledge_base_id),
                file_id=str(file.id),
                parse_job_id=str(parse_job.id),
                file_name=file.file_name,
                content=text,
                source_locator=chunk.source_locator or "",
                source_type=chunk.source_type or "text",
                heading_path=chunk.heading_path or [],
                is_active=True,
            ))
        bm25_index_client.upsert_chunks(documents=bm25_documents)

    return {
        "file_id": str(file_id),
        "chunks_indexed": len(active_chunks),
        "status": "ok",
    }


def get_request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
