from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import KnowledgeBaseStatus


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    description: str | None
    status: str
    file_count: int
    chunk_count: int
    created_by: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseResponse]
    total: int
    page: int
    page_size: int


class KnowledgeBasePublicSummaryResponse(BaseModel):
    active_count: int
    deployment_day: int


class KnowledgeBaseCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class KnowledgeBaseUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: KnowledgeBaseStatus | None = None
