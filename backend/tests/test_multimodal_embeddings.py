import httpx
import pytest

from app.core.errors import ApiError
from app.rag.embeddings.base import EmbeddingRequest
from app.rag.embeddings.qwen_multimodal import (
    QWEN_MULTIMODAL_EMBEDDING_PATH,
    QwenMultimodalEmbeddingProvider,
)


def test_qwen_provider_builds_payload_for_text_image_and_video() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["json"] = request.read().decode()
        return httpx.Response(
            200,
            json={
                "output": {
                    "embeddings": [
                        {"embedding": [0.1, 0.2]},
                        {"embedding": [0.3, 0.4]},
                        {"embedding": [0.5, 0.6]},
                    ]
                }
            },
        )

    provider = QwenMultimodalEmbeddingProvider(
        model_name="qwen-mm",
        api_key="test-key",
        base_url="https://dashscope.test",
        transport=httpx.MockTransport(handler),
    )

    results = provider.embed_batch(
        [
            EmbeddingRequest(input_type="text", content="hello"),
            EmbeddingRequest(
                input_type="image",
                content="oss://bucket/image.png",
                metadata={"image_id": "img-1"},
            ),
            EmbeddingRequest(input_type="video", content="oss://bucket/video.mp4"),
        ]
    )

    assert captured["url"] == f"https://dashscope.test{QWEN_MULTIMODAL_EMBEDDING_PATH}"
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"] == "Bearer test-key"
    payload = captured["json"]
    assert isinstance(payload, str)
    assert '"model":"qwen-mm"' in payload.replace(" ", "")
    assert '"text":"hello"' in payload.replace(" ", "")
    assert '"image":"oss://bucket/image.png"' in payload.replace(" ", "")
    assert '"video":"oss://bucket/video.mp4"' in payload.replace(" ", "")
    assert [result.dimension for result in results] == [2, 2, 2]
    assert [result.input_type for result in results] == ["text", "image", "video"]


def test_qwen_provider_embed_single_returns_dimension() -> None:
    provider = QwenMultimodalEmbeddingProvider(
        model_name="qwen-mm",
        api_key="test-key",
        base_url="https://dashscope.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"data": [{"embedding": [1, 2, 3]}]})
        ),
    )

    result = provider.embed(EmbeddingRequest(input_type="text", content="hello"))

    assert result.vector == [1.0, 2.0, 3.0]
    assert result.model == "qwen-mm"
    assert result.dimension == 3


def test_qwen_provider_raises_when_api_key_missing() -> None:
    provider = QwenMultimodalEmbeddingProvider(
        model_name="qwen-mm",
        api_key="",
        base_url="https://dashscope.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
    )

    with pytest.raises(ApiError) as exc_info:
        provider.embed(EmbeddingRequest(input_type="text", content="hello"))

    assert exc_info.value.code == "QWEN_API_KEY_MISSING"


def test_qwen_provider_raises_on_http_error() -> None:
    provider = QwenMultimodalEmbeddingProvider(
        model_name="qwen-mm",
        api_key="test-key",
        base_url="https://dashscope.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(500, json={})),
    )

    with pytest.raises(ApiError) as exc_info:
        provider.embed(EmbeddingRequest(input_type="text", content="hello"))

    assert exc_info.value.code == "UPSTREAM_SERVICE_ERROR"


def test_qwen_provider_raises_on_empty_or_unsupported_vectors() -> None:
    empty_provider = QwenMultimodalEmbeddingProvider(
        model_name="qwen-mm",
        api_key="test-key",
        base_url="https://dashscope.test",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"output": {"embeddings": [[]]}})
        ),
    )
    unsupported_provider = QwenMultimodalEmbeddingProvider(
        model_name="qwen-mm",
        api_key="test-key",
        base_url="https://dashscope.test",
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"ok": True})),
    )

    with pytest.raises(ApiError):
        empty_provider.embed(EmbeddingRequest(input_type="text", content="hello"))
    with pytest.raises(ApiError):
        unsupported_provider.embed(EmbeddingRequest(input_type="text", content="hello"))
