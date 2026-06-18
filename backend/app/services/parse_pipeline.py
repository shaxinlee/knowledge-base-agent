import asyncio
import logging
from contextlib import suppress
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import File, ParseJob, ParseJobStatus
from app.services.bm25_index import (
    BM25IndexClientProtocol,
    get_bm25_index_client,
)
from app.services.chunks import generate_chunks_for_parse_job
from app.services.document_blocks import normalize_parse_job_result
from app.services.embedding import EmbeddingClientProtocol, get_embedding_client
from app.services.files import poll_mineru_parse_job, submit_queued_parse_job
from app.services.image_descriptions import (
    ImageDescriptionClientProtocol,
    enrich_image_chunk_descriptions,
    get_image_description_client,
)
from app.services.indexing import index_parse_job
from app.services.knowledge_overall import rebuild_knowledge_base_overall
from app.services.mineru import MineruClient, get_mineru_client
from app.services.object_storage import ObjectStorage, get_object_storage
from app.services.vector_index import VectorIndexClientProtocol, get_vector_index_client

logger = logging.getLogger(__name__)

RUNNABLE_PARSE_JOB_STATUSES = (
    ParseJobStatus.QUEUED.value,
    ParseJobStatus.PARSING.value,
    ParseJobStatus.NORMALIZING.value,
    ParseJobStatus.CHUNKING.value,
    ParseJobStatus.EMBEDDING.value,
)

TERMINAL_PARSE_JOB_STATUSES = {
    ParseJobStatus.INDEXED.value,
    ParseJobStatus.PARTIALLY_INDEXED.value,
    ParseJobStatus.FAILED.value,
    ParseJobStatus.CANCELLED.value,
}


def process_pending_parse_jobs_once(
    *,
    session_factory: sessionmaker[Session],
    batch_size: int,
    storage: ObjectStorage | None = None,
    mineru_client: MineruClient | None = None,
    embedding_client: EmbeddingClientProtocol | None = None,
    vector_index_client: VectorIndexClientProtocol | None = None,
    bm25_index_client: BM25IndexClientProtocol | None = None,
    image_description_client: ImageDescriptionClientProtocol | None = None,
) -> int:
    storage = storage or get_object_storage()
    mineru_client = mineru_client or get_mineru_client()
    embedding_client = embedding_client or get_embedding_client()
    vector_index_client = vector_index_client or get_vector_index_client()
    bm25_index_client = bm25_index_client or get_bm25_index_client()
    image_description_client = image_description_client or get_image_description_client()

    with session_factory() as db:
        parse_job_ids = list(
            db.scalars(
                select(ParseJob.id)
                .join(File, File.id == ParseJob.file_id)
                .where(
                    ParseJob.status.in_(RUNNABLE_PARSE_JOB_STATUSES),
                    File.latest_parse_job_id == ParseJob.id,
                    File.deleted_at.is_(None),
                )
                .order_by(ParseJob.created_at.asc())
                .limit(batch_size)
            ).all()
        )

    processed_count = 0
    for parse_job_id in parse_job_ids:
        try:
            processed_count += int(
                run_parse_job_until_waiting(
                    session_factory=session_factory,
                    parse_job_id=parse_job_id,
                    storage=storage,
                    mineru_client=mineru_client,
                    embedding_client=embedding_client,
                    vector_index_client=vector_index_client,
                    bm25_index_client=bm25_index_client,
                    image_description_client=image_description_client,
                )
            )
        except Exception:
            logger.exception("Parse job worker failed to advance parse_job_id=%s", parse_job_id)
    return processed_count


def run_parse_job_until_waiting(
    *,
    session_factory: sessionmaker[Session],
    parse_job_id: UUID,
    storage: ObjectStorage,
    mineru_client: MineruClient,
    embedding_client: EmbeddingClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
    image_description_client: ImageDescriptionClientProtocol | None = None,
    max_steps: int = 8,
) -> bool:
    image_description_client = image_description_client or get_image_description_client()
    advanced = False
    with session_factory() as db:
        for _step in range(max_steps):
            did_advance = advance_parse_job_once(
                db,
                parse_job_id=parse_job_id,
                storage=storage,
                mineru_client=mineru_client,
                embedding_client=embedding_client,
                vector_index_client=vector_index_client,
                bm25_index_client=bm25_index_client,
                image_description_client=image_description_client,
            )
            if not did_advance:
                break
            advanced = True

            db.expire_all()
            parse_job = db.get(ParseJob, parse_job_id)
            if parse_job is None or parse_job.status in TERMINAL_PARSE_JOB_STATUSES:
                break
    return advanced


def run_parse_job_background(
    *,
    session_factory: sessionmaker[Session],
    parse_job_id: UUID,
    storage: ObjectStorage,
    mineru_client: MineruClient,
    embedding_client: EmbeddingClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
    image_description_client: ImageDescriptionClientProtocol | None = None,
) -> None:
    try:
        run_parse_job_until_waiting(
            session_factory=session_factory,
            parse_job_id=parse_job_id,
            storage=storage,
            mineru_client=mineru_client,
            embedding_client=embedding_client,
            vector_index_client=vector_index_client,
            bm25_index_client=bm25_index_client,
            image_description_client=image_description_client,
        )
    except Exception:
        logger.exception("Background parse job failed for parse_job_id=%s", parse_job_id)


def advance_parse_job_once(
    db: Session,
    *,
    parse_job_id: UUID,
    storage: ObjectStorage,
    mineru_client: MineruClient,
    embedding_client: EmbeddingClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
    image_description_client: ImageDescriptionClientProtocol,
) -> bool:
    parse_job = db.get(ParseJob, parse_job_id)
    if parse_job is None:
        return False

    file = db.get(File, parse_job.file_id)
    if file is None or file.deleted_at is not None or file.latest_parse_job_id != parse_job.id:
        return False

    previous_status = parse_job.status
    if parse_job.status == ParseJobStatus.QUEUED.value:
        submit_queued_parse_job(
            db,
            file=file,
            parse_job=parse_job,
            storage=storage,
            mineru_client=mineru_client,
        )
    elif parse_job.status == ParseJobStatus.PARSING.value:
        poll_mineru_parse_job(
            db,
            file=file,
            parse_job=parse_job,
            storage=storage,
            mineru_client=mineru_client,
        )
    elif parse_job.status == ParseJobStatus.NORMALIZING.value:
        normalize_parse_job_result(db, file=file, parse_job=parse_job, storage=storage)
    elif parse_job.status == ParseJobStatus.CHUNKING.value:
        generate_chunks_for_parse_job(db, file=file, parse_job=parse_job)
        try:
            rebuild_knowledge_base_overall(
                db,
                knowledge_base_id=file.knowledge_base_id,
                storage=storage,
            )
        except Exception:
            logger.exception(
                "Failed to update knowledge overall after chunking parse_job_id=%s",
                parse_job_id,
            )
    elif parse_job.status == ParseJobStatus.EMBEDDING.value:
        enrich_image_chunk_descriptions(
            db,
            file=file,
            parse_job=parse_job,
            storage=storage,
            image_description_client=image_description_client,
        )
        index_parse_job(
            db,
            file=file,
            parse_job=parse_job,
            embedding_client=embedding_client,
            vector_index_client=vector_index_client,
            bm25_index_client=bm25_index_client,
            storage=storage,
        )
    else:
        return False

    db.expire_all()
    updated_parse_job = db.get(ParseJob, parse_job_id)
    return updated_parse_job is not None and updated_parse_job.status != previous_status


class ParseJobWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        poll_interval_seconds: float,
        batch_size: int,
    ) -> None:
        self.session_factory = session_factory
        self.poll_interval_seconds = poll_interval_seconds
        self.batch_size = batch_size
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="parse-job-worker")

    async def stop(self) -> None:
        if self._task is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._stop_event = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await asyncio.to_thread(
                process_pending_parse_jobs_once,
                session_factory=self.session_factory,
                batch_size=self.batch_size,
            )
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.poll_interval_seconds,
                )
