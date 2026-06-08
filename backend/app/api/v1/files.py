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
from app.services.files import (
    delete_file,
    get_file,
    get_file_status,
    list_file_debug_chunks,
    list_files,
    retry_parse_file,
    upload_files,
)
from app.services.parse_pipeline import run_parse_job_background
from app.services.bm25_index import BM25IndexClientProtocol, get_bm25_index_client
from app.services.embedding import EmbeddingClientProtocol, get_embedding_client
from app.services.mineru import MineruClient, get_mineru_client
from app.services.object_storage import ObjectStorage, get_object_storage
from app.services.vector_index import VectorIndexClientProtocol, get_vector_index_client

router = APIRouter(tags=["Files"])

__all__ = [
    "get_embedding_client",
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


@router.get("/files/{file_id}/chunks", response_model=ChunkDebugListResponse)
def read_file_chunks(
    file_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> ChunkDebugListResponse:
    return list_file_debug_chunks(db, file_id=file_id, page=page, page_size=page_size)


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


def get_request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
