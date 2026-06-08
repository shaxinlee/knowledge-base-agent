from datetime import datetime

from pydantic import BaseModel, Field

from app.models import FeedbackRating


class FeedbackCreateRequest(BaseModel):
    rating: FeedbackRating
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: str
    message_id: str
    user_id: str
    knowledge_base_id: str
    rating: str
    comment: str | None
    query_text: str | None
    retrieved_chunk_ids: list[str] | None
    final_cited_chunk_ids: list[str] | None
    model_name: str | None
    prompt_version: str | None
    embedding_model: str | None
    reranker_model: str | None
    latency_ms: int | None
    token_input: int | None
    token_output: int | None
    created_at: datetime
    updated_at: datetime
