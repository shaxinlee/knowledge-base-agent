from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class FileResponse(BaseModel):
    id: str
    knowledge_base_id: str
    file_name: str
    file_ext: str
    mime_type: str | None
    size_bytes: int
    file_hash: str
    status: str
    latest_parse_job_id: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ParseJobResponse(BaseModel):
    id: str
    file_id: str
    status: str
    progress: int
    error_code: str | None
    error_message: str | None
    logs: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class FileUploadItem(BaseModel):
    file: FileResponse
    parse_job: ParseJobResponse


class FileUploadWarning(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class FileUploadResponse(BaseModel):
    uploaded: list[FileUploadItem]
    warnings: list[FileUploadWarning]


class FileListResponse(BaseModel):
    items: list[FileResponse]
    total: int
    page: int
    page_size: int


class FileStatusResponse(BaseModel):
    file_id: str
    file_status: str
    latest_parse_job: ParseJobResponse | None


class ChunkDebugResponse(BaseModel):
    id: str
    file_id: str
    knowledge_base_id: str
    content: str
    source_locator: str
    token_count: int
    is_active: bool
    created_at: datetime


class ChunkDebugListResponse(BaseModel):
    items: list[ChunkDebugResponse]
    total: int
    page: int
    page_size: int
