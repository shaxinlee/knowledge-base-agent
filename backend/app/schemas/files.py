from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document_summaries import ChunkKnowledgeExtractionResponse


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
    description: str | None = None
    modality: str = "text"
    image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    image_alt: str | None = None
    asset_paths: list[str] = Field(default_factory=list)
    document_block_types: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_locator: str
    token_count: int
    is_active: bool
    created_at: datetime
    knowledge_extraction: ChunkKnowledgeExtractionResponse | None = None


class ChunkDebugListResponse(BaseModel):
    items: list[ChunkDebugResponse]
    total: int
    page: int
    page_size: int
