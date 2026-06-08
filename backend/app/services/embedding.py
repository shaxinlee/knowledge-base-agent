from collections.abc import Sequence
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError
from app.rag.embeddings.base import EmbeddingRequest
from app.rag.embeddings.qwen_multimodal import QwenMultimodalEmbeddingProvider


class EmbeddingClientProtocol(Protocol):
    model: str

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        pass


class EmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        api_mode: bool = False,
        timeout_seconds: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.api_mode = api_mode
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []

        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    build_embedding_url(self.base_url, api_mode=self.api_mode),
                    headers=build_embedding_headers(self.api_key),
                    json=build_embedding_payload(
                        model=self.model,
                        texts=texts,
                        api_mode=self.api_mode,
                    ),
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Embedding API request failed.",
                status_code=502,
                details={"service": "embedding-api", "error": str(exc)},
            ) from exc

        payload = response.json()
        vectors = parse_embedding_vectors(payload)
        if len(vectors) != len(texts):
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Embedding service returned an unexpected number of vectors.",
                status_code=502,
                details={
                    "service": "embedding-service",
                    "expected": len(texts),
                    "actual": len(vectors),
                },
            )
        return vectors


class LocalDemoEmbeddingClient:
    model = "local-demo-fixture-embedding"

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [build_local_demo_vector(text) for text in texts]


class QwenMultimodalTextEmbeddingClient:
    def __init__(self, *, provider: QwenMultimodalEmbeddingProvider) -> None:
        self.provider = provider
        self.model = provider.model_name

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        results = self.provider.embed_batch(
            [EmbeddingRequest(input_type="text", content=text) for text in texts]
        )
        return [result.vector for result in results]


def build_local_demo_vector(text: str) -> list[float]:
    normalized = "".join(text.lower().split())
    if not normalized:
        return [0.0, 1.0]
    length_component = min(float(len(normalized)), 200.0) / 200.0
    hash_component = sum((index + 1) * ord(char) for index, char in enumerate(normalized))
    return [length_component, float(hash_component % 1000) / 1000.0]


def parse_embedding_vectors(payload: Any) -> list[list[float]]:
    if isinstance(payload, dict):
        for key in ("vectors", "embeddings"):
            value = payload.get(key)
            if isinstance(value, list):
                return normalize_vectors(value)

        data = payload.get("data")
        if isinstance(data, list):
            openai_style_vectors = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                embedding = item.get("embedding")
                if isinstance(embedding, list):
                    openai_style_vectors.append(embedding)
            if openai_style_vectors:
                return normalize_vectors(openai_style_vectors)

    raise ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="Embedding API returned an unsupported response shape.",
        status_code=502,
        details={"service": "embedding-api"},
    )


def build_embedding_url(base_url: str, *, api_mode: bool) -> str:
    if base_url.endswith(("/embed", "/embeddings")):
        return base_url
    return f"{base_url}/embeddings" if api_mode else f"{base_url}/embed"


def build_embedding_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def build_embedding_payload(
    *, model: str, texts: Sequence[str], api_mode: bool
) -> dict[str, object]:
    if api_mode:
        return {"model": model, "input": list(texts)}
    return {"model": model, "texts": list(texts)}


def normalize_vectors(raw_vectors: list[Any]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for raw_vector in raw_vectors:
        if not isinstance(raw_vector, list):
            raise invalid_vector_error()
        vector: list[float] = []
        for value in raw_vector:
            if not isinstance(value, int | float):
                raise invalid_vector_error()
            vector.append(float(value))
        if not vector:
            raise invalid_vector_error()
        vectors.append(vector)
    return vectors


def invalid_vector_error() -> ApiError:
    return ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="Embedding service returned invalid vectors.",
        status_code=502,
        details={"service": "embedding-service"},
    )


def get_embedding_client() -> EmbeddingClientProtocol:
    settings = get_settings()
    if settings.demo_fixture_enabled:
        return LocalDemoEmbeddingClient()
    if should_use_qwen_multimodal_embedding(settings.embedding_model):
        return QwenMultimodalTextEmbeddingClient(
            provider=QwenMultimodalEmbeddingProvider(
                model_name=settings.embedding_model or settings.qwen_embedding_model,
                api_key=settings.qwen_api_key or settings.embedding_api_key,
                base_url=settings.qwen_base_url,
            )
        )
    if settings.embedding_api_base_url.strip():
        return EmbeddingClient(
            base_url=settings.embedding_api_base_url,
            model=settings.embedding_model,
            api_key=settings.embedding_api_key,
            api_mode=True,
        )
    return EmbeddingClient(
        base_url=settings.embedding_service_url,
        model=settings.embedding_model,
    )


def should_use_qwen_multimodal_embedding(model: str) -> bool:
    normalized_model = model.lower().strip()
    return normalized_model.startswith("qwen") and "vl" in normalized_model
