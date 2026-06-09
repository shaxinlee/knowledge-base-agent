from pydantic import BaseModel, Field


class RetrievalSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    vector_top_k: int = Field(default=50, ge=1, le=100)
    full_text_top_k: int = Field(default=50, ge=1, le=100)
    top_k: int = Field(default=8, ge=1, le=20)


class RetrievalResultItem(BaseModel):
    chunk_id: str
    file_id: str
    file_name: str
    source_locator: str
    excerpt: str
    score: float
    source: str
    modality: str = "text"
    image_url: str | None = None
    image_urls: list[str] = Field(default_factory=list)
    image_alt: str | None = None


class RetrievalSearchResponse(BaseModel):
    knowledge_base_id: str
    query: str
    items: list[RetrievalResultItem]
    total: int
