from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeGraphNode(BaseModel):
    id: str
    file_id: str
    document_summary_id: str
    file_name: str
    file_ext: str
    knowledge_base_id: str
    knowledge_base_name: str
    summary: str
    summary_status: str
    relation_count: int


class KnowledgeGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    similarity: float
    cross_knowledge_base: bool


class CommunitySummaryResponse(BaseModel):
    knowledge_base_id: str
    knowledge_base_name: str
    status: Literal["pending", "running", "completed", "failed", "not_ready"]
    summary: str | None = None
    document_count: int = 0
    model_name: str | None = None
    prompt_version: str
    reduction_level: int = 0
    error_code: str | None = None
    error_message: str | None = None
    updated_at: datetime | None = None


class KnowledgeGraphResponse(BaseModel):
    status: Literal["pending", "running", "completed", "failed"]
    source_fingerprint: str | None = None
    document_count: int
    total_document_count: int
    summarized_document_count: int
    pending_summary_count: int
    failed_summary_count: int
    not_ready_document_count: int
    relation_count: int
    embedding_model: str | None = None
    similarity_threshold: float
    max_relations_per_document: int
    nodes: list[KnowledgeGraphNode]
    edges: list[KnowledgeGraphEdge]
    communities: list[CommunitySummaryResponse]
    updated_at: datetime | None = None


class KnowledgeGraphRefreshRequest(BaseModel):
    force_embeddings: bool = False


class KnowledgeGraphQuery(BaseModel):
    knowledge_base_id: str | None = None
    include_cross_knowledge_base: bool = True
    min_similarity: float = Field(default=0.45, ge=0, le=1)
