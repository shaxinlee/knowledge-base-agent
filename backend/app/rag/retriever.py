from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.rag.query_router import Modality, RouteDecision

EvidenceModality = Literal["text", "table", "image", "metadata"]
RetrieverCallable = Callable[[str, int], list["Evidence"]]


class ImageBlock(BaseModel):
    image_id: str
    doc_id: str
    file_name: str
    page: int | None = None
    image_path: str
    image_type: str | None = None
    caption: str | None = None
    ocr_text: str | None = None
    surrounding_text: str | None = None
    embedding_text: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_embedding_text(self) -> "ImageBlock":
        if self.embedding_text:
            return self
        section_path = self.metadata.get("section_path")
        parts = [
            self.caption,
            self.ocr_text,
            self.surrounding_text,
            self.file_name,
            str(section_path) if section_path else None,
        ]
        self.embedding_text = "\n".join(part for part in parts if part)
        return self


class Evidence(BaseModel):
    evidence_id: str
    modality: EvidenceModality
    content: str
    score: float
    source: dict[str, object]
    raw: dict[str, object] = Field(default_factory=dict)


class MultimodalRetriever:
    def __init__(
        self,
        *,
        text_retriever: RetrieverCallable | None = None,
        table_retriever: RetrieverCallable | None = None,
        image_retriever: RetrieverCallable | None = None,
        metadata_retriever: RetrieverCallable | None = None,
    ) -> None:
        self.retrievers: dict[Modality, RetrieverCallable | None] = {
            "text": text_retriever,
            "table": table_retriever,
            "image": image_retriever,
            "metadata": metadata_retriever,
        }

    def retrieve(self, *, query: str, route_decision: RouteDecision) -> list[Evidence]:
        from app.rag.fusion import weighted_rrf_fusion

        result_groups: dict[str, list[Evidence]] = {}
        route_weights: dict[str, float] = {}
        for route in route_decision.routes:
            if not route.enabled:
                continue
            retriever = self.retrievers.get(route.modality)
            if retriever is None:
                continue
            result_groups[route.modality] = retriever(query, route.top_k)
            route_weights[route.modality] = route.weight
        return weighted_rrf_fusion(result_groups=result_groups, route_weights=route_weights)


def image_block_to_evidence(image_block: ImageBlock, *, score: float) -> Evidence:
    return Evidence(
        evidence_id=image_block.image_id,
        modality="image",
        content=image_block.embedding_text or "",
        score=score,
        source={
            "doc_id": image_block.doc_id,
            "file_name": image_block.file_name,
            "page": image_block.page,
            "image_path": image_block.image_path,
            "caption": image_block.caption,
            "ocr_text": image_block.ocr_text,
        },
        raw=image_block.model_dump(mode="json"),
    )
