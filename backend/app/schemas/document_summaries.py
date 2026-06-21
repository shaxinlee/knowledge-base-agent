from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SemanticRole = Literal[
    "DESCRIPTION",
    "DEFINITION",
    "RULE",
    "REQUIREMENT",
    "PROCEDURE",
    "DECISION",
    "ACTION_ITEM",
    "FACT",
    "CLAIM",
    "RESULT",
    "RISK",
    "LIMITATION",
    "REFERENCE",
    "OTHER",
]
EntityType = Literal[
    "PERSON",
    "ORG",
    "ROLE",
    "PRODUCT",
    "PROJECT",
    "SYSTEM",
    "DOCUMENT",
    "LOCATION",
    "DATE",
    "TIME",
    "MONEY",
    "METRIC",
    "METHOD",
    "POLICY",
    "EVENT",
    "OTHER",
]
StatementType = Literal[
    "FACT",
    "RULE",
    "REQUIREMENT",
    "PROCEDURE",
    "DECISION",
    "ACTION_ITEM",
    "CLAIM",
    "RESULT",
    "RISK",
    "LIMITATION",
    "DEFINITION",
]
QualityFlag = Literal[
    "OCR_NOISE",
    "INCOMPLETE_SENTENCE",
    "DUPLICATE_CONTENT",
    "LOW_INFORMATION",
    "TABLE_CONTENT",
    "FIGURE_CAPTION",
    "HEADER_FOOTER",
    "REFERENCE_LIST",
    "NONE",
]


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    normalized_name: str | None
    type: EntityType


class ExtractedAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statement: str
    statement_type: StatementType
    subject: str | None
    predicate: str | None
    object: str | None
    conditions: list[str]
    time_scope: str | None
    polarity: Literal["POSITIVE", "NEGATIVE", "NEUTRAL"]
    certainty: Literal["HIGH", "MEDIUM", "LOW"]
    evidence_text: str


class ChunkKnowledgeExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    semantic_role: SemanticRole
    short_summary: str
    topics: list[str]
    keywords: list[str]
    entities: list[ExtractedEntity]
    assertions: list[ExtractedAssertion]
    importance: float = Field(ge=0, le=1)
    quality_flags: list[QualityFlag]

    @model_validator(mode="after")
    def validate_quality_flags(self) -> "ChunkKnowledgeExtractionPayload":
        if "NONE" in self.quality_flags and len(self.quality_flags) > 1:
            raise ValueError("quality_flags NONE cannot be combined with other flags")
        return self


class ChunkKnowledgeExtractionResponse(BaseModel):
    status: Literal["pending", "running", "completed", "failed"]
    extraction: ChunkKnowledgeExtractionPayload | None = None
    model_name: str | None = None
    prompt_version: str
    attempt_count: int
    error_code: str | None = None
    error_message: str | None = None


class DocumentSummaryResponse(BaseModel):
    file_id: str
    parse_job_id: str | None
    status: Literal[
        "pending",
        "running",
        "completed",
        "partially_completed",
        "failed",
        "not_ready",
    ]
    summary: str | None = None
    chunk_total: int = 0
    chunk_completed: int = 0
    chunk_succeeded: int = 0
    chunk_failed: int = 0
    failed_chunk_ids: list[str] = Field(default_factory=list)
    model_name: str | None = None
    chunk_prompt_version: str
    document_prompt_version: str
    reduction_level: int = 0
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentSummaryRetryRequest(BaseModel):
    force: bool = False
