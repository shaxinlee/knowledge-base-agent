from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel, Field

EmbeddingInputType = Literal["text", "image", "video"]


class EmbeddingRequest(BaseModel):
    input_type: EmbeddingInputType
    content: str = Field(min_length=1)
    metadata: dict[str, object] | None = None


class EmbeddingResult(BaseModel):
    vector: list[float]
    model: str
    dimension: int
    input_type: EmbeddingInputType


class BaseEmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        pass

    @abstractmethod
    def embed_batch(self, requests: list[EmbeddingRequest]) -> list[EmbeddingResult]:
        pass
