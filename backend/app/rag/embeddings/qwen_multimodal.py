from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError
from app.rag.embeddings.base import (
    BaseEmbeddingProvider,
    EmbeddingRequest,
    EmbeddingResult,
)

QWEN_MULTIMODAL_EMBEDDING_PATH = (
    "/api/v1/services/embeddings/multimodal-embedding/multimodal-embedding"
)


class QwenMultimodalEmbeddingProvider(BaseEmbeddingProvider):
    def __init__(
        self,
        model_name: str = "",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_seconds: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        settings = get_settings()
        self.model_name = model_name or settings.qwen_embedding_model
        self.api_key = settings.qwen_api_key if api_key is None else api_key
        self.base_url = (base_url if base_url is not None else settings.qwen_base_url).rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return self.embed_batch([request])[0]

    def embed_batch(self, requests: list[EmbeddingRequest]) -> list[EmbeddingResult]:
        if not requests:
            return []
        if not self.api_key:
            raise ApiError(
                code="QWEN_API_KEY_MISSING",
                message="Qwen API key is not configured.",
                status_code=503,
                details={"service": "qwen-multimodal-embedding"},
            )

        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    build_qwen_embedding_url(self.base_url),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=build_qwen_embedding_payload(
                        model_name=self.model_name,
                        requests=requests,
                    ),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Qwen multimodal embedding request failed.",
                status_code=502,
                details={"service": "qwen-multimodal-embedding", "error": str(exc)},
            ) from exc

        vectors = parse_qwen_vectors(response.json())
        validate_qwen_vectors(vectors=vectors, expected_count=len(requests))
        return [
            EmbeddingResult(
                vector=vector,
                model=self.model_name,
                dimension=len(vector),
                input_type=request.input_type,
            )
            for request, vector in zip(requests, vectors, strict=True)
        ]


def build_qwen_embedding_url(base_url: str) -> str:
    if base_url.endswith(QWEN_MULTIMODAL_EMBEDDING_PATH):
        return base_url
    return f"{base_url}{QWEN_MULTIMODAL_EMBEDDING_PATH}"


def build_qwen_embedding_payload(
    *, model_name: str, requests: list[EmbeddingRequest]
) -> dict[str, object]:
    return {
        "model": model_name,
        "input": {
            "contents": [build_qwen_content(request) for request in requests],
        },
    }


def build_qwen_content(request: EmbeddingRequest) -> dict[str, object]:
    content: dict[str, object] = {request.input_type: request.content}
    if request.metadata:
        content["metadata"] = request.metadata
    return content


def parse_qwen_vectors(payload: Any) -> list[list[float]]:
    if not isinstance(payload, dict):
        raise unsupported_response_error()

    vectors = parse_vector_list(payload.get("vectors")) or parse_vector_list(
        payload.get("embeddings")
    )
    if vectors is not None:
        return vectors

    data_vectors = parse_items_with_embedding(payload.get("data"))
    if data_vectors is not None:
        return data_vectors

    output = payload.get("output")
    if isinstance(output, dict):
        output_vectors = parse_vector_list(output.get("embeddings")) or parse_items_with_embedding(
            output.get("embeddings")
        )
        if output_vectors is not None:
            return output_vectors

    raise unsupported_response_error()


def parse_items_with_embedding(value: object) -> list[list[float]] | None:
    if not isinstance(value, list):
        return None
    vectors: list[list[float]] = []
    for item in value:
        if not isinstance(item, dict):
            return None
        embedding = item.get("embedding")
        if not isinstance(embedding, list):
            return None
        vectors.append(normalize_vector(embedding))
    return vectors if vectors else None


def parse_vector_list(value: object) -> list[list[float]] | None:
    if not isinstance(value, list) or not value:
        return None
    if all(isinstance(item, int | float) for item in value):
        return [normalize_vector(value)]
    vectors: list[list[float]] = []
    for item in value:
        if not isinstance(item, list):
            return None
        vectors.append(normalize_vector(item))
    return vectors


def normalize_vector(raw_vector: list[object]) -> list[float]:
    vector: list[float] = []
    for value in raw_vector:
        if not isinstance(value, int | float):
            raise invalid_vector_error()
        vector.append(float(value))
    if not vector:
        raise invalid_vector_error()
    return vector


def validate_qwen_vectors(*, vectors: list[list[float]], expected_count: int) -> None:
    if len(vectors) != expected_count:
        raise ApiError(
            code="QWEN_EMBEDDING_VECTOR_COUNT_MISMATCH",
            message="Qwen embedding vector count does not match request count.",
            status_code=502,
            details={"expected": expected_count, "actual": len(vectors)},
        )
    dimension = len(vectors[0]) if vectors else 0
    if dimension <= 0:
        raise invalid_vector_error()
    if any(len(vector) != dimension for vector in vectors):
        raise ApiError(
            code="QWEN_EMBEDDING_VECTOR_DIMENSION_MISMATCH",
            message="Qwen embedding vectors have inconsistent dimensions.",
            status_code=502,
            details={"dimension": dimension},
        )


def unsupported_response_error() -> ApiError:
    return ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="Qwen multimodal embedding returned an unsupported response shape.",
        status_code=502,
        details={"service": "qwen-multimodal-embedding"},
    )


def invalid_vector_error() -> ApiError:
    return ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="Qwen multimodal embedding returned invalid vectors.",
        status_code=502,
        details={"service": "qwen-multimodal-embedding"},
    )
