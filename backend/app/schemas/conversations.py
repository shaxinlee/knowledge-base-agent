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
    modality: str = "text"
    image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    image_alt: str | None = None


class MessageAttachmentInput(BaseModel):
    type: str = Field(default="image")
    file_name: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=100)
    data_url: str = Field(min_length=1)


class MessageAttachmentResponse(BaseModel):
    id: str
    type: str
    file_name: str
    media_type: str
    size_bytes: int
    url: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: datetime
    citations: list[CitationResponse]
    attachments: list[MessageAttachmentResponse] = Field(default_factory=list)
    feedback_rating: str | None = None
    visual_result_mode: str | None = None


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse]


class ConversationListResponse(BaseModel):
    items: list[ConversationResponse]
    total: int
    page: int
    page_size: int


class MessageCreateRequest(BaseModel):
    content: str = Field(default="", max_length=8000)
    stream: bool = False
    enable_thinking: bool = False
    attachments: list[MessageAttachmentInput] = Field(default_factory=list, max_length=1)


class MessageCreateResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse
