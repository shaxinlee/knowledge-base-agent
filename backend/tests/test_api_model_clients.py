import json
from collections.abc import Sequence
from typing import Any, cast

import httpx

from app.schemas.retrieval import RetrievalResultItem
from app.rag.embeddings.qwen_multimodal import QWEN_MULTIMODAL_EMBEDDING_PATH
from app.services.bm25_index import BM25ChunkDocument, OpenSearchBM25IndexClient
from app.services.embedding import (
    EmbeddingClient,
    QwenMultimodalTextEmbeddingClient,
    should_use_qwen_multimodal_embedding,
)
from app.services.indexing import clear_indexing_error_log, embed_texts_in_batches
from app.rag.embeddings.qwen_multimodal import QwenMultimodalEmbeddingProvider
from app.services.image_descriptions import (
    ImageDescriptionInput,
    OpenAIVisionImageDescriptionClient,
)
from app.services.llm import LLMApiClient
from app.services.reranker import DashScopeTextRerankerClient, RerankerClient


class RecordingEmbeddingClient:
    model = "recording-embedding"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.requests.append(list(texts))
        return [[float(len(text))] for text in texts]


def test_embedding_api_client_calls_openai_compatible_embeddings() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2]},
                    {"embedding": [0.3, 0.4]},
                ]
            },
        )

    client = EmbeddingClient(
        base_url="https://embedding.example/v1",
        model="bge-m3",
        api_key="embedding-key",
        api_mode=True,
        transport=httpx.MockTransport(handler),
    )

    vectors = client.embed_texts(["alpha", "beta"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == "https://embedding.example/v1/embeddings"
    assert captured["payload"] == {"model": "bge-m3", "input": ["alpha", "beta"]}
    headers = cast(dict[str, Any], captured["headers"])
    assert headers["authorization"] == "Bearer embedding-key"


def test_opensearch_bm25_client_creates_ik_mapping_upserts_and_searches() -> None:
    captured: dict[str, object] = {"requests": []}

    def handler(request: httpx.Request) -> httpx.Response:
        requests = cast(list[dict[str, object]], captured["requests"])
        body = request.content.decode("utf-8")
        requests.append({"method": request.method, "url": str(request.url), "body": body})
        if request.method == "GET" and str(request.url).endswith("/chunks_bm25"):
            return httpx.Response(404)
        if request.method == "PUT" and str(request.url).endswith("/chunks_bm25"):
            return httpx.Response(200, json={"acknowledged": True})
        if request.method == "POST" and str(request.url).endswith("/_bulk"):
            return httpx.Response(200, json={"errors": False, "items": []})
        if request.method == "POST" and str(request.url).endswith("/chunks_bm25/_search"):
            return httpx.Response(
                200,
                json={
                    "hits": {
                        "hits": [
                            {
                                "_score": 12.5,
                                "_source": {"chunk_id": "chunk-1"},
                            }
                        ]
                    }
                },
            )
        return httpx.Response(500)

    client = OpenSearchBM25IndexClient(
        base_url="http://opensearch.test:9200",
        index_name="chunks_bm25",
        index_analyzer="ik_max_word",
        search_analyzer="ik_smart",
        transport=httpx.MockTransport(handler),
    )

    client.ensure_index()
    client.upsert_chunks(
        documents=[
            BM25ChunkDocument(
                chunk_id="chunk-1",
                knowledge_base_id="kb-1",
                file_id="file-1",
                parse_job_id="job-1",
                file_name="manual.pdf",
                content="井下落鱼可视化工具",
                source_locator="pdf:p1",
                source_type="pdf",
                heading_path=["工具说明"],
            )
        ]
    )
    hits = client.search(query="井下落鱼", knowledge_base_id="kb-1", limit=5)

    requests = cast(list[dict[str, object]], captured["requests"])
    mapping_payload = json.loads(cast(str, requests[1]["body"]))
    assert mapping_payload["settings"]["analysis"]["analyzer"]["kb_ik_index"] == {
        "type": "custom",
        "tokenizer": "ik_max_word",
    }
    assert mapping_payload["settings"]["analysis"]["analyzer"]["kb_ik_search"] == {
        "type": "custom",
        "tokenizer": "ik_smart",
    }
    bulk_body = cast(str, requests[2]["body"])
    assert '"chunk_id":"chunk-1"' in bulk_body
    assert '"content":"井下落鱼可视化工具"' in bulk_body
    search_payload = json.loads(cast(str, requests[3]["body"]))
    assert search_payload["query"]["bool"]["filter"] == [
        {"term": {"knowledge_base_id": "kb-1"}},
        {"term": {"is_active": True}},
    ]
    assert hits[0].chunk_id == "chunk-1"
    assert hits[0].score == 12.5


def test_qwen_multimodal_text_embedding_client_uses_provider_endpoint() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "output": {
                    "embeddings": [
                        {"embedding": [0.1, 0.2]},
                        {"embedding": [0.3, 0.4]},
                    ]
                }
            },
        )

    client = QwenMultimodalTextEmbeddingClient(
        provider=QwenMultimodalEmbeddingProvider(
            model_name="qwen3-vl-embedding",
            api_key="qwen-key",
            base_url="https://dashscope.example",
            transport=httpx.MockTransport(handler),
        )
    )

    vectors = client.embed_texts(["alpha", "beta"])

    assert vectors == [[0.1, 0.2], [0.3, 0.4]]
    assert captured["url"] == f"https://dashscope.example{QWEN_MULTIMODAL_EMBEDDING_PATH}"
    assert captured["payload"] == {
        "model": "qwen3-vl-embedding",
        "input": {"contents": [{"text": "alpha"}, {"text": "beta"}]},
    }
    assert client.model == "qwen3-vl-embedding"


def test_qwen_multimodal_embedding_selection_only_matches_vl_models() -> None:
    assert should_use_qwen_multimodal_embedding("qwen3-vl-embedding")
    assert not should_use_qwen_multimodal_embedding("qwen3-embedding")
    assert not should_use_qwen_multimodal_embedding("bge-m3")


def test_image_description_client_calls_openai_compatible_vision_model() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "图片展示系统架构图。"}}]},
        )

    client = OpenAIVisionImageDescriptionClient(
        base_url="https://vision.example/v1",
        api_key="vision-key",
        model="qwen3.6-flash",
        temperature=0.3,
        max_tokens=640,
        transport=httpx.MockTransport(handler),
    )

    description = client.describe_image(
        ImageDescriptionInput(
            image_bytes=b"fake-png",
            media_type="image/png",
            context_text="Frontend -> Backend",
            source_locator="pdf:p1",
            file_name="architecture.pdf",
        )
    )

    assert description == "图片展示系统架构图。"
    assert captured["url"] == "https://vision.example/v1/chat/completions"
    payload = cast(dict[str, Any], captured["payload"])
    assert payload["model"] == "qwen3.6-flash"
    assert payload["temperature"] == 0.3
    assert payload["max_tokens"] == 640
    content = cast(
        list[dict[str, Any]], cast(list[dict[str, Any]], payload["messages"])[0]["content"]
    )
    assert content[0]["type"] == "text"
    assert "Frontend -> Backend" in content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    headers = cast(dict[str, Any], captured["headers"])
    assert headers["authorization"] == "Bearer vision-key"


def test_embedding_indexing_batches_requests_without_reordering_vectors() -> None:
    client = RecordingEmbeddingClient()

    vectors = embed_texts_in_batches(client, ["a", "bb", "ccc", "dddd", "eeeee"], batch_size=2)

    assert client.requests == [["a", "bb"], ["ccc", "dddd"], ["eeeee"]]
    assert vectors == [[1.0], [2.0], [3.0], [4.0], [5.0]]


def test_successful_indexing_log_cleanup_removes_stale_error() -> None:
    logs = clear_indexing_error_log(
        {
            "indexing": {"chunk_count": 1},
            "indexing_error": {"code": "OLD_ERROR"},
        }
    )

    assert logs == {"indexing": {"chunk_count": 1}}


def test_reranker_api_client_uses_api_key_and_scores() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json={"scores": [0.8, 0.2]})

    client = RerankerClient(
        base_url="https://reranker.example/api",
        model="bge-reranker",
        api_key="reranker-key",
        transport=httpx.MockTransport(handler),
    )

    scores = client.rerank(query="question", documents=["doc1", "doc2"])

    assert scores == [0.8, 0.2]
    assert captured["url"] == "https://reranker.example/api/rerank"
    assert captured["payload"] == {
        "model": "bge-reranker",
        "query": "question",
        "documents": ["doc1", "doc2"],
    }
    headers = cast(dict[str, Any], captured["headers"])
    assert headers["authorization"] == "Bearer reranker-key"


def test_dashscope_reranker_client_uses_text_rerank_endpoint_and_relevance_scores() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "output": {
                    "results": [
                        {"index": 0, "relevance_score": 0.8},
                        {"index": 1, "relevance_score": 0.2},
                    ]
                }
            },
        )

    client = DashScopeTextRerankerClient(
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="qwen3-vl-rerank",
        api_key="reranker-key",
        transport=httpx.MockTransport(handler),
    )

    scores = client.rerank(query="question", documents=["doc1", "doc2"])

    assert scores == [0.8, 0.2]
    assert (
        captured["url"]
        == "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"
    )
    assert captured["payload"] == {
        "model": "qwen3-vl-rerank",
        "input": {"query": "question", "documents": ["doc1", "doc2"]},
        "parameters": {"return_documents": False},
    }
    headers = cast(dict[str, Any], captured["headers"])
    assert headers["authorization"] == "Bearer reranker-key"


def test_llm_api_client_generates_answer_with_citation_prompt() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Answer grounded in context [1]"}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 6},
            },
        )

    client = LLMApiClient(
        base_url="https://llm.example/v1",
        api_key="llm-key",
        model="test-chat",
        transport=httpx.MockTransport(handler),
    )
    context = RetrievalResultItem(
        chunk_id="chunk-1",
        file_id="file-1",
        file_name="manual.pdf",
        source_locator="pdf:p1",
        excerpt="Grounding text.",
        score=0.9,
        source="rerank",
    )

    answer = client.generate_answer(query="What is covered?", contexts=[context])

    assert answer.content == "Answer grounded in context [1]"
    assert answer.model == "test-chat"
    assert answer.token_usage == {"prompt_tokens": 20, "completion_tokens": 6}
    assert captured["url"] == "https://llm.example/v1/chat/completions"
    payload = cast(dict[str, Any], captured["payload"])
    assert payload["model"] == "test-chat"
    assert payload["stream"] is False
    assert payload["enable_thinking"] is False
    assert payload["temperature"] == 0.5
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}
    assert "manual.pdf" in answer.raw_prompt_snapshot
    assert "pdf:p1" in answer.raw_prompt_snapshot
    assert "Grounding text." in answer.raw_prompt_snapshot
    headers = cast(dict[str, Any], captured["headers"])
    assert headers["authorization"] == "Bearer llm-key"


def test_llm_api_client_streams_openai_compatible_deltas() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=(
                'data: {"choices":[{"delta":{"content":"A"}}]}\n'
                'data: {"choices":[{"delta":{"content":"B"}}]}\n'
                "data: [DONE]\n"
            ),
        )

    client = LLMApiClient(
        base_url="https://llm.example/v1/chat/completions",
        api_key="llm-key",
        model="test-chat",
        transport=httpx.MockTransport(handler),
    )

    tokens = list(client.stream_answer(query="Q", contexts=[]))

    assert tokens == ["A", "B"]


def test_llm_api_client_can_enable_thinking_for_answer_generation() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Thoughtful answer [1]"}}]},
        )

    client = LLMApiClient(
        base_url="https://llm.example/v1",
        api_key="llm-key",
        model="test-chat",
        transport=httpx.MockTransport(handler),
    )

    client.generate_answer(query="Q", contexts=[], enable_thinking=True)

    assert captured["payload"] == {
        "model": "test-chat",
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是一个知识库问答助手。只能基于提供的上下文回答问题。"
                    "如果上下文信息不足以回答问题，请简要拒答。"
                    "每个事实陈述必须标注引用编号，格式如 [1]、[2]。"
                    "不要输出文件路径、图片 URL、资源路径、存储路径、文件名、页码、原始来源位置、"
                    "原始 HTML 标签或原始 LaTeX 代码。将表格以可读表格形式呈现，"
                    "公式以普通数学文本形式呈现。"
                ),
            },
            {
                "role": "user",
                "content": "上下文：\n\n\n问题：\nQ\n\n请基于上下文回答，并标注引用编号。",
            },
        ],
        "stream": False,
        "temperature": 0.5,
        "enable_thinking": True,
        "chat_template_kwargs": {"enable_thinking": True},
    }
