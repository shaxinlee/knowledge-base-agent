from datetime import datetime

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    knowledge_base_id: str
    title: str | None = Field(default=None, max_length=255)


class ConversationResponse(BaseModel):
    id: str
    knowledge_base_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class CitationResponse(BaseModel):
    id: str | None = None
    index: int
    file_name: str
    source_locator: str
    excerpt: str
    chunk_id: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    citations: list[CitationResponse]
    feedback_rating: str | None = None


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class MessageCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    stream: bool = False


class MessageCreateResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
