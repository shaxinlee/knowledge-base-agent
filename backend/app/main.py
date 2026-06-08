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

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    init_default_admin()
    worker: ParseJobWorker | None = None
    if settings.parse_worker_enabled:
        worker = ParseJobWorker(
            session_factory=SessionLocal,
            poll_interval_seconds=settings.parse_worker_poll_interval_seconds,
            batch_size=settings.parse_worker_batch_size,
        )
        await worker.start()
    try:
        yield
    finally:
        if worker is not None:
            await worker.stop()


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
