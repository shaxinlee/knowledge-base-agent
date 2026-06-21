import asyncio
import logging
import socket
import uuid
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.models import (
    ChunkExtractionStatus,
    ChunkKnowledgeExtraction,
    ChunkMetadata,
    DocumentSummary,
    DocumentSummaryStatus,
    File,
    ParseJob,
)
from app.schemas.document_summaries import (
    ChunkKnowledgeExtractionPayload,
    ChunkKnowledgeExtractionResponse,
    DocumentSummaryResponse,
)
from app.services.document_summary_llm import (
    CHUNK_PROMPT_VERSION,
    DOCUMENT_PROMPT_VERSION,
    ChunkPromptInput,
    DocumentSummaryLLMClient,
    DocumentSummaryLLMError,
    SummarySource,
    get_document_summary_llm_config,
)
from app.services.visual_citations import infer_chunk_modality

logger = logging.getLogger(__name__)

PRIORITY_MANUAL = 0
PRIORITY_NEW_DOCUMENT = 10
PRIORITY_BACKFILL = 20
LEASE_DURATION = timedelta(minutes=30)


@dataclass(frozen=True)
class ChunkWorkItem:
    chunk_id: UUID
    file_id: UUID
    parse_job_id: UUID
    chunk_index: int
    prompt_input: ChunkPromptInput


def enqueue_document_summary(
    db: Session,
    *,
    file: File,
    parse_job: ParseJob,
    priority: int = PRIORITY_NEW_DOCUMENT,
    force: bool = False,
) -> DocumentSummary:
    chunks = list(
        db.scalars(
            select(ChunkMetadata)
            .where(
                ChunkMetadata.file_id == file.id,
                ChunkMetadata.parse_job_id == parse_job.id,
                ChunkMetadata.is_active.is_(True),
            )
            .order_by(ChunkMetadata.chunk_index)
        ).all()
    )
    document_summary = db.scalar(
        select(DocumentSummary).where(
            DocumentSummary.file_id == file.id,
            DocumentSummary.parse_job_id == parse_job.id,
        )
    )
    status = (
        DocumentSummaryStatus.PENDING.value
        if chunks
        else DocumentSummaryStatus.NOT_READY.value
    )
    if document_summary is None:
        document_summary = DocumentSummary(
            knowledge_base_id=file.knowledge_base_id,
            file_id=file.id,
            parse_job_id=parse_job.id,
            status=status,
            priority=priority,
            chunk_total=len(chunks),
            chunk_prompt_version=CHUNK_PROMPT_VERSION,
            document_prompt_version=DOCUMENT_PROMPT_VERSION,
        )
        db.add(document_summary)
    else:
        document_summary.priority = min(document_summary.priority, priority)
        document_summary.chunk_total = len(chunks)
        if force or document_summary.status in {
            DocumentSummaryStatus.FAILED.value,
            DocumentSummaryStatus.NOT_READY.value,
        }:
            document_summary.status = status
            document_summary.summary = None
            document_summary.error_code = None
            document_summary.error_message = None
            document_summary.finished_at = None
            document_summary.worker_id = None
            document_summary.lease_expires_at = None
    for chunk in chunks:
        extraction = db.scalar(
            select(ChunkKnowledgeExtraction).where(
                ChunkKnowledgeExtraction.chunk_id == chunk.id
            )
        )
        if extraction is None:
            db.add(
                ChunkKnowledgeExtraction(
                    chunk_id=chunk.id,
                    file_id=file.id,
                    parse_job_id=parse_job.id,
                    status=ChunkExtractionStatus.PENDING.value,
                    prompt_version=CHUNK_PROMPT_VERSION,
                )
            )
        elif force:
            extraction.status = ChunkExtractionStatus.PENDING.value
            extraction.extraction = None
            extraction.short_summary = None
            extraction.attempt_count = 0
            extraction.error_code = None
            extraction.error_message = None
            extraction.started_at = None
            extraction.finished_at = None
    db.flush()
    refresh_document_summary_progress(db, document_summary)
    return document_summary


def retry_document_summary(
    db: Session,
    *,
    file_id: UUID,
    force: bool,
) -> DocumentSummaryResponse:
    file = get_visible_file(db, file_id)
    if file.latest_parse_job_id is None:
        return build_not_ready_response(file)
    parse_job = db.get(ParseJob, file.latest_parse_job_id)
    if parse_job is None:
        return build_not_ready_response(file)
    summary = enqueue_document_summary(
        db,
        file=file,
        parse_job=parse_job,
        priority=PRIORITY_MANUAL,
        force=force,
    )
    if not force:
        failed_extractions = db.scalars(
            select(ChunkKnowledgeExtraction).where(
                ChunkKnowledgeExtraction.file_id == file.id,
                ChunkKnowledgeExtraction.parse_job_id == parse_job.id,
                ChunkKnowledgeExtraction.status == ChunkExtractionStatus.FAILED.value,
            )
        ).all()
        for extraction in failed_extractions:
            extraction.status = ChunkExtractionStatus.PENDING.value
            extraction.error_code = None
            extraction.error_message = None
            extraction.finished_at = None
        if summary.chunk_total:
            summary.status = DocumentSummaryStatus.PENDING.value
            summary.summary = None
            summary.finished_at = None
            summary.error_code = None
            summary.error_message = None
            summary.worker_id = None
            summary.lease_expires_at = None
    db.commit()
    db.refresh(summary)
    return build_document_summary_response(summary)


def get_document_summary_response(db: Session, *, file_id: UUID) -> DocumentSummaryResponse:
    file = get_visible_file(db, file_id)
    if file.latest_parse_job_id is None:
        return build_not_ready_response(file)
    summary = db.scalar(
        select(DocumentSummary).where(
            DocumentSummary.file_id == file.id,
            DocumentSummary.parse_job_id == file.latest_parse_job_id,
        )
    )
    if summary is None:
        return build_not_ready_response(file)
    refresh_document_summary_progress(db, summary)
    db.commit()
    return build_document_summary_response(summary)


def get_chunk_extraction_response(
    extraction: ChunkKnowledgeExtraction | None,
) -> ChunkKnowledgeExtractionResponse | None:
    if extraction is None:
        return None
    payload = (
        ChunkKnowledgeExtractionPayload.model_validate(extraction.extraction)
        if extraction.extraction
        else None
    )
    return ChunkKnowledgeExtractionResponse(
        status=extraction.status,
        extraction=payload,
        model_name=extraction.model_name,
        prompt_version=extraction.prompt_version,
        attempt_count=extraction.attempt_count,
        error_code=extraction.error_code,
        error_message=extraction.error_message,
    )


def claim_document_summaries(
    session_factory: sessionmaker[Session],
    *,
    limit: int,
    worker_id: str,
) -> list[UUID]:
    now = datetime.now(UTC)
    with session_factory() as db:
        candidates = list(
            db.scalars(
                select(DocumentSummary)
                .join(File, File.id == DocumentSummary.file_id)
                .where(
                    File.deleted_at.is_(None),
                    File.latest_parse_job_id == DocumentSummary.parse_job_id,
                    or_(
                        DocumentSummary.status == DocumentSummaryStatus.PENDING.value,
                        (
                            (DocumentSummary.status == DocumentSummaryStatus.RUNNING.value)
                            & (
                                (DocumentSummary.lease_expires_at.is_(None))
                                | (DocumentSummary.lease_expires_at < now)
                            )
                        ),
                    ),
                )
                .order_by(DocumentSummary.priority.asc(), DocumentSummary.created_at.asc())
                .with_for_update(skip_locked=True)
                .limit(limit)
            ).all()
        )
        for summary in candidates:
            summary.status = DocumentSummaryStatus.RUNNING.value
            summary.worker_id = worker_id
            summary.lease_expires_at = now + LEASE_DURATION
            summary.started_at = summary.started_at or now
            summary.finished_at = None
            summary.error_code = None
            summary.error_message = None
        db.commit()
        return [summary.id for summary in candidates]


def release_worker_tasks(
    session_factory: sessionmaker[Session],
    *,
    worker_id: str,
) -> None:
    with session_factory() as db:
        summaries = list(
            db.scalars(
                select(DocumentSummary).where(
                    DocumentSummary.worker_id == worker_id,
                    DocumentSummary.status == DocumentSummaryStatus.RUNNING.value,
                )
            ).all()
        )
        for summary in summaries:
            db.execute(
                update(ChunkKnowledgeExtraction)
                .where(
                    ChunkKnowledgeExtraction.file_id == summary.file_id,
                    ChunkKnowledgeExtraction.parse_job_id == summary.parse_job_id,
                    ChunkKnowledgeExtraction.status == ChunkExtractionStatus.RUNNING.value,
                )
                .values(status=ChunkExtractionStatus.PENDING.value)
            )
            summary.status = DocumentSummaryStatus.PENDING.value
            summary.worker_id = None
            summary.lease_expires_at = None
        db.commit()


async def process_document_summary(
    *,
    session_factory: sessionmaker[Session],
    summary_id: UUID,
    worker_id: str,
    client: DocumentSummaryLLMClient,
    chunk_concurrency: int,
) -> None:
    work_items = await asyncio.to_thread(
        prepare_document_work,
        session_factory,
        summary_id=summary_id,
        worker_id=worker_id,
        model_name=client.model,
    )
    document_semaphore = asyncio.Semaphore(chunk_concurrency)

    async def process_chunk(item: ChunkWorkItem) -> None:
        async with document_semaphore:
            valid = await asyncio.to_thread(
                mark_chunk_running,
                session_factory,
                summary_id=summary_id,
                worker_id=worker_id,
                chunk_id=item.chunk_id,
            )
            if not valid:
                return
            try:
                extraction, attempts = await client.extract_chunk(item.prompt_input)
                await asyncio.to_thread(
                    save_chunk_success,
                    session_factory,
                    summary_id=summary_id,
                    worker_id=worker_id,
                    item=item,
                    extraction=extraction,
                    model_name=client.model,
                    attempts=attempts,
                )
            except DocumentSummaryLLMError as exc:
                await asyncio.to_thread(
                    save_chunk_failure,
                    session_factory,
                    summary_id=summary_id,
                    worker_id=worker_id,
                    item=item,
                    error_code=exc.code,
                    error_message=str(exc),
                    attempts=exc.attempts,
                    model_name=client.model,
                )
            except Exception as exc:
                logger.exception("Unexpected chunk summary failure chunk_id=%s", item.chunk_id)
                await asyncio.to_thread(
                    save_chunk_failure,
                    session_factory,
                    summary_id=summary_id,
                    worker_id=worker_id,
                    item=item,
                    error_code="CHUNK_EXTRACTION_FAILED",
                    error_message=str(exc),
                    attempts=0,
                    model_name=client.model,
                )

    await asyncio.gather(*(process_chunk(item) for item in work_items))
    sources = await asyncio.to_thread(
        load_summary_sources,
        session_factory,
        summary_id=summary_id,
        worker_id=worker_id,
    )
    if sources is None:
        return
    if not sources:
        await asyncio.to_thread(
            finish_document_failure,
            session_factory,
            summary_id=summary_id,
            worker_id=worker_id,
            error_code="NO_SUCCESSFUL_CHUNK_SUMMARIES",
            error_message="No successful chunk summaries are available.",
        )
        return
    try:
        final_summary, reduction_level = await client.summarize_document(sources)
        await asyncio.to_thread(
            finish_document_success,
            session_factory,
            summary_id=summary_id,
            worker_id=worker_id,
            summary_text=final_summary,
            model_name=client.model,
            reduction_level=reduction_level,
        )
    except DocumentSummaryLLMError as exc:
        await asyncio.to_thread(
            finish_document_failure,
            session_factory,
            summary_id=summary_id,
            worker_id=worker_id,
            error_code=exc.code,
            error_message=str(exc),
        )


def prepare_document_work(
    session_factory: sessionmaker[Session],
    *,
    summary_id: UUID,
    worker_id: str,
    model_name: str,
) -> list[ChunkWorkItem]:
    with session_factory() as db:
        summary = db.get(DocumentSummary, summary_id)
        if not is_current_summary(db, summary, worker_id=worker_id):
            return []
        assert summary is not None
        chunks = list(
            db.scalars(
                select(ChunkMetadata)
                .where(
                    ChunkMetadata.file_id == summary.file_id,
                    ChunkMetadata.parse_job_id == summary.parse_job_id,
                    ChunkMetadata.is_active.is_(True),
                )
                .order_by(ChunkMetadata.chunk_index)
            ).all()
        )
        if not chunks:
            summary.status = DocumentSummaryStatus.NOT_READY.value
            summary.chunk_total = 0
            summary.worker_id = None
            summary.lease_expires_at = None
            db.commit()
            return []
        work_items: list[ChunkWorkItem] = []
        for chunk in chunks:
            extraction = db.scalar(
                select(ChunkKnowledgeExtraction).where(
                    ChunkKnowledgeExtraction.chunk_id == chunk.id
                )
            )
            if extraction is None:
                extraction = ChunkKnowledgeExtraction(
                    chunk_id=chunk.id,
                    file_id=summary.file_id,
                    parse_job_id=summary.parse_job_id,
                    status=ChunkExtractionStatus.PENDING.value,
                    prompt_version=CHUNK_PROMPT_VERSION,
                )
                db.add(extraction)
            if (
                extraction.status == ChunkExtractionStatus.COMPLETED.value
                and extraction.prompt_version == CHUNK_PROMPT_VERSION
                and extraction.model_name == model_name
                and extraction.short_summary
            ):
                continue
            work_items.append(build_chunk_work_item(chunk))
        summary.chunk_total = len(chunks)
        summary.model_name = model_name
        summary.lease_expires_at = datetime.now(UTC) + LEASE_DURATION
        db.commit()
        return work_items


def build_chunk_work_item(chunk: ChunkMetadata) -> ChunkWorkItem:
    if chunk.page_start is None:
        page_no: str | int | None = None
    elif chunk.page_end is not None and chunk.page_end != chunk.page_start:
        page_no = f"{chunk.page_start}-{chunk.page_end}"
    else:
        page_no = chunk.page_start
    metadata = chunk.chunk_metadata or {}
    block_types = metadata.get("document_block_types")
    content_type = infer_chunk_modality(chunk)
    if isinstance(block_types, list) and block_types:
        content_type = ",".join(str(item) for item in block_types)
    return ChunkWorkItem(
        chunk_id=chunk.id,
        file_id=chunk.file_id,
        parse_job_id=chunk.parse_job_id,
        chunk_index=chunk.chunk_index,
        prompt_input=ChunkPromptInput(
            chunk_id=str(chunk.id),
            document_id=str(chunk.file_id),
            section_path=" > ".join(chunk.heading_path or []),
            page_no=page_no,
            content_type=content_type or chunk.source_type,
            chunk_text=chunk.content,
        ),
    )


def mark_chunk_running(
    session_factory: sessionmaker[Session],
    *,
    summary_id: UUID,
    worker_id: str,
    chunk_id: UUID,
) -> bool:
    with session_factory() as db:
        summary = db.get(DocumentSummary, summary_id)
        if not is_current_summary(db, summary, worker_id=worker_id):
            return False
        extraction = db.scalar(
            select(ChunkKnowledgeExtraction).where(
                ChunkKnowledgeExtraction.chunk_id == chunk_id
            )
        )
        if extraction is None:
            return False
        extraction.status = ChunkExtractionStatus.RUNNING.value
        extraction.started_at = datetime.now(UTC)
        extraction.finished_at = None
        extraction.error_code = None
        extraction.error_message = None
        assert summary is not None
        summary.lease_expires_at = datetime.now(UTC) + LEASE_DURATION
        db.commit()
        return True


def save_chunk_success(
    session_factory: sessionmaker[Session],
    *,
    summary_id: UUID,
    worker_id: str,
    item: ChunkWorkItem,
    extraction: ChunkKnowledgeExtractionPayload,
    model_name: str,
    attempts: int,
) -> None:
    with session_factory() as db:
        summary = db.get(DocumentSummary, summary_id)
        chunk = db.get(ChunkMetadata, item.chunk_id)
        if not is_current_summary(db, summary, worker_id=worker_id) or not chunk or not chunk.is_active:
            return
        row = db.scalar(
            select(ChunkKnowledgeExtraction).where(
                ChunkKnowledgeExtraction.chunk_id == item.chunk_id
            )
        )
        if row is None:
            return
        row.status = ChunkExtractionStatus.COMPLETED.value
        row.extraction = extraction.model_dump()
        row.short_summary = extraction.short_summary
        row.model_name = model_name
        row.prompt_version = CHUNK_PROMPT_VERSION
        row.attempt_count += attempts
        row.error_code = None
        row.error_message = None
        row.finished_at = datetime.now(UTC)
        assert summary is not None
        refresh_document_summary_progress(db, summary)
        summary.lease_expires_at = datetime.now(UTC) + LEASE_DURATION
        db.commit()


def save_chunk_failure(
    session_factory: sessionmaker[Session],
    *,
    summary_id: UUID,
    worker_id: str,
    item: ChunkWorkItem,
    error_code: str,
    error_message: str,
    attempts: int,
    model_name: str,
) -> None:
    with session_factory() as db:
        summary = db.get(DocumentSummary, summary_id)
        if not is_current_summary(db, summary, worker_id=worker_id):
            return
        row = db.scalar(
            select(ChunkKnowledgeExtraction).where(
                ChunkKnowledgeExtraction.chunk_id == item.chunk_id
            )
        )
        if row is None:
            return
        row.status = ChunkExtractionStatus.FAILED.value
        row.model_name = model_name
        row.prompt_version = CHUNK_PROMPT_VERSION
        row.attempt_count += attempts
        row.error_code = error_code
        row.error_message = error_message[:4000]
        row.finished_at = datetime.now(UTC)
        assert summary is not None
        refresh_document_summary_progress(db, summary)
        summary.lease_expires_at = datetime.now(UTC) + LEASE_DURATION
        db.commit()


def load_summary_sources(
    session_factory: sessionmaker[Session],
    *,
    summary_id: UUID,
    worker_id: str,
) -> list[SummarySource] | None:
    with session_factory() as db:
        summary = db.get(DocumentSummary, summary_id)
        if not is_current_summary(db, summary, worker_id=worker_id):
            return None
        assert summary is not None
        rows = db.execute(
            select(ChunkMetadata, ChunkKnowledgeExtraction)
            .join(
                ChunkKnowledgeExtraction,
                ChunkKnowledgeExtraction.chunk_id == ChunkMetadata.id,
            )
            .where(
                ChunkMetadata.file_id == summary.file_id,
                ChunkMetadata.parse_job_id == summary.parse_job_id,
                ChunkMetadata.is_active.is_(True),
                ChunkKnowledgeExtraction.status == ChunkExtractionStatus.COMPLETED.value,
            )
            .order_by(ChunkMetadata.chunk_index)
        ).all()
        refresh_document_summary_progress(db, summary)
        summary.lease_expires_at = datetime.now(UTC) + LEASE_DURATION
        db.commit()
        return [
            SummarySource(
                chunk_id=str(chunk.id),
                section_path=" > ".join(chunk.heading_path or []),
                source_locator=chunk.source_locator,
                short_summary=extraction.short_summary or "",
            )
            for chunk, extraction in rows
            if extraction.short_summary
        ]


def finish_document_success(
    session_factory: sessionmaker[Session],
    *,
    summary_id: UUID,
    worker_id: str,
    summary_text: str,
    model_name: str,
    reduction_level: int,
) -> None:
    with session_factory() as db:
        summary = db.get(DocumentSummary, summary_id)
        if not is_current_summary(db, summary, worker_id=worker_id):
            return
        assert summary is not None
        refresh_document_summary_progress(db, summary)
        summary.status = (
            DocumentSummaryStatus.COMPLETED.value
            if summary.chunk_failed == 0 and summary.chunk_succeeded == summary.chunk_total
            else DocumentSummaryStatus.PARTIALLY_COMPLETED.value
        )
        summary.summary = summary_text
        summary.model_name = model_name
        summary.reduction_level = reduction_level
        summary.error_code = None
        summary.error_message = None
        summary.finished_at = datetime.now(UTC)
        summary.worker_id = None
        summary.lease_expires_at = None
        db.commit()


def finish_document_failure(
    session_factory: sessionmaker[Session],
    *,
    summary_id: UUID,
    worker_id: str,
    error_code: str,
    error_message: str,
) -> None:
    with session_factory() as db:
        summary = db.get(DocumentSummary, summary_id)
        if not is_current_summary(db, summary, worker_id=worker_id):
            return
        assert summary is not None
        refresh_document_summary_progress(db, summary)
        summary.status = DocumentSummaryStatus.FAILED.value
        summary.error_code = error_code
        summary.error_message = error_message[:4000]
        summary.finished_at = datetime.now(UTC)
        summary.worker_id = None
        summary.lease_expires_at = None
        db.commit()


def refresh_document_summary_progress(db: Session, summary: DocumentSummary) -> None:
    counts = dict(
        db.execute(
            select(ChunkKnowledgeExtraction.status, func.count())
            .where(
                ChunkKnowledgeExtraction.file_id == summary.file_id,
                ChunkKnowledgeExtraction.parse_job_id == summary.parse_job_id,
            )
            .group_by(ChunkKnowledgeExtraction.status)
        ).all()
    )
    succeeded = int(counts.get(ChunkExtractionStatus.COMPLETED.value, 0))
    failed = int(counts.get(ChunkExtractionStatus.FAILED.value, 0))
    summary.chunk_succeeded = succeeded
    summary.chunk_failed = failed
    summary.chunk_completed = succeeded + failed
    summary.failed_chunk_ids = [
        str(chunk_id)
        for chunk_id in db.scalars(
            select(ChunkKnowledgeExtraction.chunk_id).where(
                ChunkKnowledgeExtraction.file_id == summary.file_id,
                ChunkKnowledgeExtraction.parse_job_id == summary.parse_job_id,
                ChunkKnowledgeExtraction.status == ChunkExtractionStatus.FAILED.value,
            )
        ).all()
    ]


def is_current_summary(
    db: Session,
    summary: DocumentSummary | None,
    *,
    worker_id: str,
) -> bool:
    if summary is None or summary.worker_id != worker_id:
        return False
    file = db.get(File, summary.file_id)
    return bool(
        file is not None
        and file.deleted_at is None
        and file.latest_parse_job_id == summary.parse_job_id
    )


def build_document_summary_response(summary: DocumentSummary) -> DocumentSummaryResponse:
    return DocumentSummaryResponse(
        file_id=str(summary.file_id),
        parse_job_id=str(summary.parse_job_id),
        status=summary.status,
        summary=summary.summary,
        chunk_total=summary.chunk_total,
        chunk_completed=summary.chunk_completed,
        chunk_succeeded=summary.chunk_succeeded,
        chunk_failed=summary.chunk_failed,
        failed_chunk_ids=summary.failed_chunk_ids or [],
        model_name=summary.model_name,
        chunk_prompt_version=summary.chunk_prompt_version,
        document_prompt_version=summary.document_prompt_version,
        reduction_level=summary.reduction_level,
        error_code=summary.error_code,
        error_message=summary.error_message,
        started_at=summary.started_at,
        finished_at=summary.finished_at,
        updated_at=summary.updated_at,
    )


def build_not_ready_response(file: File) -> DocumentSummaryResponse:
    return DocumentSummaryResponse(
        file_id=str(file.id),
        parse_job_id=str(file.latest_parse_job_id) if file.latest_parse_job_id else None,
        status=DocumentSummaryStatus.NOT_READY.value,
        chunk_prompt_version=CHUNK_PROMPT_VERSION,
        document_prompt_version=DOCUMENT_PROMPT_VERSION,
    )


def get_visible_file(db: Session, file_id: UUID) -> File:
    file = db.scalar(select(File).where(File.id == file_id, File.deleted_at.is_(None)))
    if file is None:
        raise ApiError(
            code="FILE_NOT_FOUND",
            message="File was not found.",
            status_code=404,
            details={"file_id": str(file_id)},
        )
    return file


class DocumentSummaryWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        settings: Settings | None = None,
        client: DocumentSummaryLLMClient | None = None,
        request_semaphore: asyncio.Semaphore | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.worker_id = f"{socket.gethostname()}:{uuid.uuid4()}"
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None
        self._request_semaphore = request_semaphore or asyncio.Semaphore(
            self.settings.document_summary_global_request_concurrency
        )
        self._client = client
        self._owns_client = client is None

    async def start(self) -> None:
        if self._task is not None:
            return
        if self._client is None:
            base_url, api_key, model = get_document_summary_llm_config()
            if not base_url or not model:
                logger.warning(
                    "Document summary worker is disabled at runtime because LLM base URL "
                    "or model is not configured."
                )
                return
            self._client = DocumentSummaryLLMClient(
                base_url=base_url,
                api_key=api_key,
                model=model,
                settings=self.settings,
                request_semaphore=self._request_semaphore,
            )
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="document-summary-worker")

    async def stop(self) -> None:
        if self._task is not None:
            assert self._stop_event is not None
            self._stop_event.set()
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
            self._stop_event = None
            await asyncio.to_thread(
                release_worker_tasks,
                self.session_factory,
                worker_id=self.worker_id,
            )
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        assert self._client is not None
        active: set[asyncio.Task[None]] = set()
        try:
            while not self._stop_event.is_set():
                active = {task for task in active if not task.done()}
                available = self.settings.document_summary_document_concurrency - len(active)
                if available > 0:
                    try:
                        summary_ids = await asyncio.to_thread(
                            claim_document_summaries,
                            session_factory=self.session_factory,
                            worker_id=self.worker_id,
                            limit=available,
                        )
                    except Exception:
                        logger.exception(
                            "Document summary worker could not claim tasks; it will retry."
                        )
                        summary_ids = []
                    for summary_id in summary_ids:
                        task = asyncio.create_task(
                            process_document_summary(
                                session_factory=self.session_factory,
                                summary_id=summary_id,
                                worker_id=self.worker_id,
                                client=self._client,
                                chunk_concurrency=(
                                    self.settings.document_summary_chunk_concurrency
                                ),
                            ),
                            name=f"document-summary-{summary_id}",
                        )
                        task.add_done_callback(log_summary_task_failure)
                        active.add(task)
                if active:
                    _done, _pending = await asyncio.wait(
                        active,
                        timeout=self.settings.document_summary_worker_poll_interval_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                else:
                    with suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=(
                                self.settings.document_summary_worker_poll_interval_seconds
                            ),
                        )
        finally:
            for task in active:
                task.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)


def log_summary_task_failure(task: asyncio.Task[None]) -> None:
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.error(
            "Document summary task failed unexpectedly.",
            exc_info=(type(error), error, error.__traceback__),
        )
