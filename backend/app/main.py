import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import ApiError, api_error_handler
from app.db.init import init_default_admin
from app.db.session import SessionLocal
from app.services.parse_pipeline import ParseJobWorker
from app.services.document_summaries import DocumentSummaryWorker
from app.services.knowledge_graph import KnowledgeGraphWorker

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_default_admin()
    worker: ParseJobWorker | None = None
    summary_worker: DocumentSummaryWorker | None = None
    graph_worker: KnowledgeGraphWorker | None = None
    model_request_semaphore = asyncio.Semaphore(
        settings.document_summary_global_request_concurrency
    )
    if settings.parse_worker_enabled:
        worker = ParseJobWorker(
            session_factory=SessionLocal,
            poll_interval_seconds=settings.parse_worker_poll_interval_seconds,
            batch_size=settings.parse_worker_batch_size,
        )
        await worker.start()
    if settings.document_summary_enabled:
        summary_worker = DocumentSummaryWorker(
            session_factory=SessionLocal,
            settings=settings,
            request_semaphore=model_request_semaphore,
        )
        await summary_worker.start()
    if settings.knowledge_graph_enabled:
        graph_worker = KnowledgeGraphWorker(
            session_factory=SessionLocal,
            request_semaphore=model_request_semaphore,
            settings=settings,
        )
        await graph_worker.start()
    # Expose workers via app.state so API endpoints can reload LLM clients
    # when model settings change.
    _app.state.document_summary_worker = summary_worker
    _app.state.knowledge_graph_worker = graph_worker

    try:
        yield
    finally:
        if worker is not None:
            await worker.stop()
        if summary_worker is not None:
            await summary_worker.stop()
        if graph_worker is not None:
            await graph_worker.stop()


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
)

app.add_exception_handler(ApiError, api_error_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.backend_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
