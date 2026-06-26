import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import (
    ChunkMetadata,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    ParseJob,
    ParseJobStatus,
    User,
)
from app.schemas.files import (
    ChunkDebugListResponse,
    FileListResponse,
    FileResponse,
    FileStatusResponse,
    FileUploadItem,
    FileUploadResponse,
    ParseJobResponse,
)
from app.services.audit_logs import create_audit_log
from app.services.bm25_index import BM25IndexClientProtocol
from app.services.chunks import list_chunks
from app.services.mineru import MineruClient, extract_first_result
from app.services.object_storage import ObjectStorage
from app.services.vector_index import VectorIndexClientProtocol

SUPPORTED_FILE_EXTENSIONS = {
    ".pdf",
    ".md",
    ".docx",
    ".txt",
    ".xlsx",
    ".xls",
    ".csv",
    ".pptx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
}


def list_files(
    db: Session,
    *,
    knowledge_base_id: UUID,
    page: int,
    page_size: int,
    keyword: str | None,
    status: FileStatus | None,
) -> FileListResponse:
    require_active_knowledge_base(db, knowledge_base_id)
    normalized_page = max(page, 1)
    normalized_page_size = min(max(page_size, 1), 100)
    filters: list[ColumnElement[bool]] = [
        File.knowledge_base_id == knowledge_base_id,
        File.deleted_at.is_(None),
    ]

    if keyword:
        filters.append(File.file_name.ilike(f"%{keyword}%"))
    if status is not None:
        filters.append(File.status == status.value)

    base_query = select(File).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    files = db.scalars(
        base_query.order_by(File.created_at.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()

    return FileListResponse(
        items=[build_file_response(file) for file in files],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


async def upload_files(
    db: Session,
    *,
    knowledge_base_id: UUID,
    uploads: list[UploadFile],
    force: bool,
    actor: User,
    storage: ObjectStorage,
    ip_address: str | None,
    user_agent: str | None,
) -> FileUploadResponse:
    knowledge_base = require_active_knowledge_base(db, knowledge_base_id)
    settings = get_settings()

    if len(uploads) > settings.max_batch_upload_count:
        raise ApiError(
            code="TOO_MANY_FILES",
            message="Too many files in one upload request.",
            status_code=400,
            details={"max_batch_upload_count": settings.max_batch_upload_count},
        )

    prepared_files = [await prepare_upload(upload) for upload in uploads]
    ensure_unique_incoming_names(prepared_files)
    duplicate_hashes = find_duplicate_hashes(db, knowledge_base_id, prepared_files)
    if duplicate_hashes and not force:
        raise ApiError(
            code="DUPLICATE_FILE_HASH",
            message="File content already exists in this knowledge base.",
            status_code=409,
            details={"duplicates": duplicate_hashes, "can_force_upload": True},
        )

    uploaded: list[FileUploadItem] = []
    for prepared_file in prepared_files:
        ensure_file_name_available(db, knowledge_base_id, prepared_file["file_name"])
        file = File(
            knowledge_base_id=knowledge_base.id,
            file_name=prepared_file["file_name"],
            file_ext=prepared_file["file_ext"],
            mime_type=prepared_file["mime_type"],
            file_size=prepared_file["size_bytes"],
            file_hash=prepared_file["file_hash"],
            storage_bucket=settings.raw_files_bucket,
            storage_key="",
            status=FileStatus.QUEUED.value,
            created_by=actor.id,
        )
        db.add(file)
        db.flush()

        storage_key = build_raw_file_storage_key(
            knowledge_base_id=knowledge_base.id,
            file_id=file.id,
            file_name=file.file_name,
        )
        storage.put_object(
            bucket=settings.raw_files_bucket,
            key=storage_key,
            data=prepared_file["content"],
            content_type=file.mime_type,
            metadata={
                "file_id": str(file.id),
                "knowledge_base_id": str(knowledge_base.id),
                "file_hash": file.file_hash,
            },
        )
        file.storage_key = storage_key

        parse_job = ParseJob(
            file_id=file.id,
            knowledge_base_id=knowledge_base.id,
            status=ParseJobStatus.QUEUED.value,
            progress=0,
            created_by=actor.id,
        )
        db.add(parse_job)
        db.flush()
        file.latest_parse_job_id = parse_job.id

        create_audit_log(
            db,
            actor_id=actor.id,
            action="upload_file",
            resource_type="file",
            resource_id=file.id,
            details={
                "knowledge_base_id": str(knowledge_base.id),
                "file_name": file.file_name,
                "file_hash": file.file_hash,
                "force": force,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        uploaded.append(
            FileUploadItem(
                file=build_file_response(file), parse_job=build_parse_job_response(parse_job)
            )
        )

    db.commit()
    return FileUploadResponse(uploaded=uploaded, warnings=[])


def get_file(db: Session, *, file_id: UUID) -> FileResponse:
    file = require_visible_file(db, file_id)
    return build_file_response(file)


def get_file_status(db: Session, *, file_id: UUID) -> FileStatusResponse:
    file = require_visible_file(db, file_id)
    parse_job = get_latest_parse_job(db, file)
    return FileStatusResponse(
        file_id=str(file.id),
        file_status=file.status,
        latest_parse_job=build_parse_job_response(parse_job) if parse_job else None,
    )


def submit_queued_parse_job(
    db: Session,
    *,
    file: File,
    parse_job: ParseJob,
    storage: ObjectStorage,
    mineru_client: MineruClient,
) -> None:
    content = storage.get_object(bucket=file.storage_bucket, key=file.storage_key)
    file.status = FileStatus.PROCESSING.value
    try:
        submission = mineru_client.submit_file(
            file_name=file.file_name,
            data_id=str(parse_job.id),
            content=content,
        )
    except Exception as exc:
        error_message = get_exception_message(exc)
        parse_job.status = ParseJobStatus.FAILED.value
        parse_job.progress = 0
        parse_job.error_code = "MINERU_SUBMIT_FAILED"
        parse_job.error_message = error_message
        parse_job.finished_at = datetime.now(UTC)
        parse_job.logs = merge_logs(
            parse_job.logs,
            {"mineru_submit_error": {"message": error_message}},
        )
        file.status = FileStatus.FAILED.value
        db.commit()
        return

    parse_job.status = ParseJobStatus.PARSING.value
    parse_job.progress = 10
    parse_job.started_at = datetime.now(UTC)
    parse_job.logs = merge_logs(
        parse_job.logs,
        {
            "mineru": {
                "batch_id": submission.batch_id,
                "data_id": submission.data_id,
                "submit_response": submission.raw_response,
            }
        },
    )
    db.commit()


def retry_parse_file(
    db: Session,
    *,
    file_id: UUID,
    actor: User,
) -> ParseJobResponse:
    file = require_visible_file(db, file_id)
    require_active_knowledge_base(db, file.knowledge_base_id)

    parse_job = ParseJob(
        file_id=file.id,
        knowledge_base_id=file.knowledge_base_id,
        status=ParseJobStatus.QUEUED.value,
        progress=0,
        logs={"provider": "mineru", "mode": "api_v4_file_urls_batch"},
        created_by=actor.id,
    )
    db.add(parse_job)
    db.flush()
    file.latest_parse_job_id = parse_job.id
    file.status = FileStatus.PROCESSING.value

    db.commit()
    db.refresh(parse_job)
    return build_parse_job_response(parse_job)


def delete_file(
    db: Session,
    *,
    file_id: UUID,
    actor: User,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    file = require_visible_file(db, file_id)
    before = build_file_snapshot(file)
    active_chunk_ids = list_active_chunk_ids(db, file_id=file.id)
    vector_index_client.delete_points(
        point_ids=[str(chunk_id) for chunk_id in active_chunk_ids]
    )
    bm25_index_client.delete_chunks(chunk_ids=[str(chunk_id) for chunk_id in active_chunk_ids])

    if active_chunk_ids:
        db.execute(
            update(ChunkMetadata)
            .where(
                ChunkMetadata.file_id == file.id,
                ChunkMetadata.is_active.is_(True),
            )
            .values(is_active=False)
        )
    file.status = FileStatus.DELETED.value
    file.deleted_at = file.deleted_at or datetime.now(UTC)
    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="delete_file",
        resource_type="file",
        resource_id=file.id,
        details={
            "before": before,
            "deleted_chunk_count": len(active_chunk_ids),
            "qdrant_points_deleted": len(active_chunk_ids),
            "qdrant_collection": vector_index_client.collection_name,
            "bm25_documents_deleted": len(active_chunk_ids),
            "bm25_provider": bm25_index_client.provider,
            "bm25_index": bm25_index_client.index_name,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()


def list_active_chunk_ids(db: Session, *, file_id: UUID) -> list[UUID]:
    return list(
        db.scalars(
            select(ChunkMetadata.id).where(
                ChunkMetadata.file_id == file_id,
                ChunkMetadata.is_active.is_(True),
            )
        ).all()
    )


def poll_mineru_parse_job(
    db: Session,
    *,
    file: File,
    parse_job: ParseJob,
    storage: ObjectStorage,
    mineru_client: MineruClient,
) -> None:
    mineru_logs = get_mineru_logs(parse_job)
    batch_id = str(mineru_logs.get("batch_id") or "")
    data_id = str(mineru_logs.get("data_id") or parse_job.id)
    if not batch_id:
        return

    batch_result = mineru_client.get_batch_result(batch_id=batch_id)
    result_item = extract_first_result(batch_result, data_id=data_id)
    if result_item is None:
        parse_job.logs = merge_logs(parse_job.logs, {"mineru_latest_result": batch_result})
        db.commit()
        return

    state = normalize_mineru_state(result_item)
    parse_job.logs = merge_logs(
        parse_job.logs,
        {"mineru_latest_result": batch_result, "mineru_latest_state": state},
    )
    if state in {"done", "completed", "success"}:
        result_url = str(result_item.get("full_zip_url") or "")
        if not result_url:
            mark_mineru_parse_job_failed(
                parse_job=parse_job,
                file=file,
                error_code="MINERU_RESULT_MISSING",
                error_message="MinerU parse completed but full_zip_url is missing.",
            )
            db.commit()
            return

        result_content = mineru_client.download_result(url=result_url)
        result_key = build_parsed_result_storage_key(parse_job=parse_job, file=file)
        settings = get_settings()
        storage.put_object(
            bucket=settings.parsed_results_bucket,
            key=result_key,
            data=result_content,
            content_type="application/zip",
            metadata={
                "file_id": str(file.id),
                "parse_job_id": str(parse_job.id),
                "knowledge_base_id": str(file.knowledge_base_id),
                "mineru_batch_id": batch_id,
            },
        )
        parse_job.logs = merge_logs(
            parse_job.logs,
            {
                "parsed_result": {
                    "bucket": settings.parsed_results_bucket,
                    "key": result_key,
                    "source_url": result_url,
                    "content_type": "application/zip",
                }
            },
        )
        parse_job.status = ParseJobStatus.NORMALIZING.value
        parse_job.progress = 40
        file.status = FileStatus.PROCESSING.value
        db.commit()
    elif state in {"failed", "error"}:
        mark_mineru_parse_job_failed(
            parse_job=parse_job,
            file=file,
            error_code="MINERU_PARSE_FAILED",
            error_message=str(
                result_item.get("err_msg") or result_item.get("message") or "MinerU parse failed."
            ),
        )
    db.commit()


def list_file_debug_chunks(
    db: Session,
    *,
    file_id: UUID,
    page: int,
    page_size: int,
) -> ChunkDebugListResponse:
    file = require_visible_file(db, file_id)
    return list_chunks(db, file_id=file.id, page=page, page_size=page_size)


async def prepare_upload(upload: UploadFile) -> dict[str, Any]:
    settings = get_settings()
    raw_file_name = Path(upload.filename or "").name
    file_ext = Path(raw_file_name).suffix.lower()

    if not raw_file_name or file_ext not in SUPPORTED_FILE_EXTENSIONS:
        raise ApiError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Unsupported file type.",
            status_code=415,
            details={
                "file_name": raw_file_name,
                "supported_extensions": sorted(SUPPORTED_FILE_EXTENSIONS),
            },
        )

    content = await upload.read()
    max_file_size = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_file_size:
        raise ApiError(
            code="FILE_TOO_LARGE",
            message="File size exceeds the configured limit.",
            status_code=413,
            details={"file_name": raw_file_name, "max_file_size_mb": settings.max_file_size_mb},
        )

    return {
        "file_name": raw_file_name,
        "file_ext": file_ext,
        "mime_type": upload.content_type,
        "size_bytes": len(content),
        "file_hash": hashlib.sha256(content).hexdigest(),
        "content": content,
    }


def ensure_unique_incoming_names(prepared_files: list[dict[str, Any]]) -> None:
    seen_names: set[str] = set()
    for prepared_file in prepared_files:
        file_name = str(prepared_file["file_name"])
        if file_name in seen_names:
            raise ApiError(
                code="DUPLICATE_FILE_NAME",
                message="File name already exists in this knowledge base.",
                status_code=409,
                details={"file_name": file_name},
            )
        seen_names.add(file_name)


def find_duplicate_hashes(
    db: Session, knowledge_base_id: UUID, prepared_files: list[dict[str, Any]]
) -> list[dict[str, str]]:
    hashes = {str(prepared_file["file_hash"]) for prepared_file in prepared_files}
    if not hashes:
        return []

    existing_files = db.scalars(
        select(File).where(
            File.knowledge_base_id == knowledge_base_id,
            File.deleted_at.is_(None),
            File.file_hash.in_(hashes),
        )
    ).all()
    duplicates: list[dict[str, str]] = []
    for prepared_file in prepared_files:
        for existing_file in existing_files:
            if (
                existing_file.file_hash == prepared_file["file_hash"]
                and existing_file.file_name != prepared_file["file_name"]
            ):
                duplicates.append(
                    {
                        "incoming_file_name": str(prepared_file["file_name"]),
                        "existing_file_id": str(existing_file.id),
                        "existing_file_name": existing_file.file_name,
                        "file_hash": existing_file.file_hash,
                    }
                )
    return duplicates


def ensure_file_name_available(db: Session, knowledge_base_id: UUID, file_name: str) -> None:
    existing = db.scalar(
        select(File).where(
            File.knowledge_base_id == knowledge_base_id,
            File.deleted_at.is_(None),
            File.file_name == file_name,
        )
    )
    if existing is not None:
        raise ApiError(
            code="DUPLICATE_FILE_NAME",
            message="File name already exists in this knowledge base.",
            status_code=409,
            details={"file_name": file_name},
        )


def require_active_knowledge_base(db: Session, knowledge_base_id: UUID) -> KnowledgeBase:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None or knowledge_base.status != KnowledgeBaseStatus.ACTIVE.value:
        raise ApiError(
            code="KNOWLEDGE_BASE_INACTIVE",
            message="Knowledge base does not exist or is not active.",
            status_code=409,
        )
    return knowledge_base


def require_visible_file(db: Session, file_id: UUID) -> File:
    file = db.get(File, file_id)
    if file is None or file.deleted_at is not None:
        raise_file_not_found()
    return file


def raise_file_not_found() -> NoReturn:
    raise ApiError(code="RESOURCE_NOT_FOUND", message="File was not found.", status_code=404)


def get_latest_parse_job(db: Session, file: File) -> ParseJob | None:
    if file.latest_parse_job_id is None:
        return None
    return db.get(ParseJob, file.latest_parse_job_id)


def get_mineru_logs(parse_job: ParseJob) -> dict[str, Any]:
    logs = parse_job.logs or {}
    mineru_logs = logs.get("mineru")
    return mineru_logs if isinstance(mineru_logs, dict) else {}


def get_exception_message(exc: Exception) -> str:
    if isinstance(exc, ApiError):
        return exc.message
    return str(exc)


def merge_logs(existing_logs: dict[str, Any] | None, new_logs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing_logs or {})
    for key, value in new_logs.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            nested = dict(merged[key])
            nested.update(value)
            merged[key] = nested
        else:
            merged[key] = value
    return merged


def normalize_mineru_state(result_item: dict[str, Any]) -> str:
    for key in ("state", "status"):
        value = result_item.get(key)
        if value is not None:
            return str(value).lower()
    return ""


def mark_mineru_parse_job_failed(
    *,
    parse_job: ParseJob,
    file: File,
    error_code: str,
    error_message: str,
) -> None:
    parse_job.status = ParseJobStatus.FAILED.value
    parse_job.progress = 0
    parse_job.error_code = error_code
    parse_job.error_message = error_message
    parse_job.finished_at = datetime.now(UTC)
    parse_job.logs = merge_logs(
        parse_job.logs,
        {"mineru_error": {"code": error_code, "message": error_message}},
    )
    file.status = FileStatus.FAILED.value


def build_parsed_result_storage_key(*, parse_job: ParseJob, file: File) -> str:
    return (
        f"knowledge-bases/{file.knowledge_base_id}/files/{file.id}/"
        f"parse-jobs/{parse_job.id}/mineru-full.zip"
    )


def build_raw_file_storage_key(*, knowledge_base_id: UUID, file_id: UUID, file_name: str) -> str:
    return f"knowledge-bases/{knowledge_base_id}/files/{file_id}/{file_name}"


def build_file_response(file: File) -> FileResponse:
    return FileResponse(
        id=str(file.id),
        knowledge_base_id=str(file.knowledge_base_id),
        file_name=file.file_name,
        file_ext=file.file_ext,
        mime_type=file.mime_type,
        size_bytes=file.file_size,
        file_hash=file.file_hash,
        status=file.status,
        latest_parse_job_id=str(file.latest_parse_job_id) if file.latest_parse_job_id else None,
        created_by=str(file.created_by),
        created_at=file.created_at,
        updated_at=file.updated_at,
    )


def build_parse_job_response(parse_job: ParseJob) -> ParseJobResponse:
    return ParseJobResponse(
        id=str(parse_job.id),
        file_id=str(parse_job.file_id),
        status=parse_job.status,
        progress=parse_job.progress,
        error_code=parse_job.error_code,
        error_message=parse_job.error_message,
        logs=parse_job.logs,
        started_at=parse_job.started_at,
        finished_at=parse_job.finished_at,
        created_at=parse_job.created_at,
        updated_at=parse_job.updated_at,
    )


def build_file_snapshot(file: File) -> dict[str, Any]:
    return {
        "id": str(file.id),
        "knowledge_base_id": str(file.knowledge_base_id),
        "file_name": file.file_name,
        "file_hash": file.file_hash,
        "status": file.status,
    }
