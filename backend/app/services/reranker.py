from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError
from app.services.model_settings import get_model_settings


class RerankerClientProtocol(Protocol):
    model: str

    def rerank(self, *, query: str, documents: Sequence[str]) -> list[float]:
        pass


class RerankerClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self._vllm_mode = is_vllm_score_url(self.base_url)

    def rerank(self, *, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                if self._vllm_mode:
                    url, payload = self._build_vllm_score_request(query, documents)
                else:
                    url = build_reranker_url(self.base_url)
                    payload = {"model": self.model, "query": query, "documents": list(documents)}
                response = client.post(
                    url,
                    headers=build_reranker_headers(self.api_key),
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Reranker API request failed.",
                status_code=502,
                details={"service": "reranker-api", "error": str(exc)},
            ) from exc

        scores = parse_reranker_scores(response.json(), expected_count=len(documents))
        return scores

    def _build_vllm_score_request(
        self, query: str, documents: Sequence[str]
    ) -> tuple[str, dict[str, object]]:
        """Build vLLM /v1/score API request with text_1/text_2 format."""
        url = self.base_url.rstrip("/")
        if not url.endswith("/score"):
            if url.endswith("/v1"):
                url = f"{url}/score"
            else:
                url = f"{url}/score"
        payload = {
            "model": self.model,
            "text_1": query,
            "text_2": list(documents),
        }
        return url, payload


class DashScopeTextRerankerClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_seconds: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = normalize_dashscope_base_url(base_url).rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def rerank(self, *, query: str, documents: Sequence[str]) -> list[float]:
        if not documents:
            return []
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/api/v1/services/rerank/text-rerank/text-rerank",
                    headers=build_reranker_headers(self.api_key),
                    json={
                        "model": self.model,
                        "input": {"query": query, "documents": list(documents)},
                        "parameters": {"return_documents": False},
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Reranker API request failed.",
                status_code=502,
                details={
                    "service": "dashscope-reranker-api",
                    "error": str(exc),
                    "response": build_error_response_excerpt(exc),
                },
            ) from exc

        scores = parse_reranker_scores(response.json(), expected_count=len(documents))
        return scores


class LocalDemoRerankerClient:
    model = "local-demo-fixture-reranker"

    def rerank(self, *, query: str, documents: Sequence[str]) -> list[float]:
        query_terms = build_demo_terms(query)
        if not query_terms:
            return [0.0 for _document in documents]
        scores: list[float] = []
        for index, document in enumerate(documents):
            document_terms = build_demo_terms(document)
            overlap = len(query_terms & document_terms)
            scores.append(float(overlap) + (1.0 / float(index + 10)))
        return scores


def is_vllm_score_url(base_url: str) -> bool:
    """Detect if the base_url is vLLM /v1/score API format."""
    normalized = base_url.lower().rstrip("/")
    return (
        normalized.endswith("/v1")
        or normalized.endswith("/v1/score")
        or normalized.endswith("/score")
    )


def build_reranker_url(base_url: str) -> str:
    if base_url.endswith("/rerank"):
        return base_url
    return f"{base_url}/rerank"


def build_reranker_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def normalize_dashscope_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "https://dashscope.aliyuncs.com"


def build_error_response_excerpt(exc: httpx.HTTPError) -> str | None:
    response = getattr(exc, "response", None)
    if response is None:
        return None
    text = response.text
    return text[:500] if isinstance(text, str) else None


def should_use_dashscope_reranker(*, base_url: str, model: str) -> bool:
    normalized_base_url = base_url.lower()
    normalized_model = model.lower()
    # 本地 vLLM / OpenAI 兼容接口不走 DashScope 专用 API 路径
    if any(host in normalized_base_url for host in (
        "localhost",
        "127.0.0.1",
        "0.0.0.0",
        "host.docker.internal",
        "host.docker",
        "/v1",
    )):
        return False
    if "dashscope.aliyuncs.com" in normalized_base_url:
        return True
    # 仅当 base_url 明确指向阿里云 DashScope 域名时才使用 DashScope 客户端
    return False


def build_demo_terms(text: str) -> set[str]:
    normalized = text.lower()
    terms = {term for term in normalized.split() if term}
    terms.update(char for char in normalized if char.strip())
    return terms


def parse_reranker_scores(payload: Any, *, expected_count: int) -> list[float]:
    if isinstance(payload, dict):
        scores = payload.get("scores")
        if isinstance(scores, list):
            return normalize_scores(scores, expected_count=expected_count)

        # vLLM /v1/score API returns {"data": [{"index": 0, "score": 0.xxx}, ...]}
        data = payload.get("data")
        if isinstance(data, list):
            return parse_indexed_scores(data, expected_count=expected_count)

        results = payload.get("results")
        if isinstance(results, list):
            return parse_indexed_scores(results, expected_count=expected_count)

        output = payload.get("output")
        if isinstance(output, dict):
            output_results = output.get("results")
            if isinstance(output_results, list):
                return parse_indexed_scores(output_results, expected_count=expected_count)

    raise ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="Reranker service returned an unsupported response shape.",
        status_code=502,
        details={"service": "reranker-service"},
    )


def normalize_scores(raw_scores: list[Any], *, expected_count: int) -> list[float]:
    if len(raw_scores) != expected_count:
        raise ApiError(
            code="UPSTREAM_SERVICE_ERROR",
            message="Reranker service returned an unexpected number of scores.",
            status_code=502,
            details={
                "service": "reranker-service",
                "expected": expected_count,
                "actual": len(raw_scores),
            },
        )
    scores: list[float] = []
    for score in raw_scores:
        if not isinstance(score, int | float):
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Reranker service returned invalid scores.",
                status_code=502,
                details={"service": "reranker-service"},
            )
        scores.append(float(score))
    return scores


def parse_indexed_scores(results: list[Any], *, expected_count: int) -> list[float]:
    ordered_scores = [0.0] * expected_count
    found_indexes: set[int] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        index = item.get("index")
        score = item.get("score")
        if not isinstance(score, int | float):
            score = item.get("relevance_score")
        if (
            isinstance(index, int)
            and 0 <= index < expected_count
            and isinstance(score, int | float)
        ):
            ordered_scores[index] = float(score)
            found_indexes.add(index)
    if len(found_indexes) == expected_count:
        return ordered_scores
    raise ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="Reranker service returned an unsupported response shape.",
        status_code=502,
        details={"service": "reranker-service"},
    )


def get_reranker_client() -> RerankerClientProtocol:
    settings = get_settings()
    model_settings = get_model_settings().reranker
    base_url = model_settings.base_url.strip()
    model = model_settings.model.strip() or settings.reranker_model
    api_key = model_settings.api_key or settings.reranker_api_key
    if settings.demo_fixture_enabled:
        return LocalDemoRerankerClient()
    if base_url and base_url != settings.reranker_service_url:
        if should_use_dashscope_reranker(
            base_url=base_url,
            model=model,
        ):
            return DashScopeTextRerankerClient(
                base_url=base_url,
                model=model,
                api_key=api_key,
            )
        return RerankerClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
        )
    return RerankerClient(
        base_url=base_url or settings.reranker_service_url,
        model=model,
    )
