import json

import httpx
from pytest import MonkeyPatch

from app.core.config import get_settings
from app.rag.query_router import (
    LLMKnowledgeSearchRouter,
    LLMQueryRouter,
    RuleBasedKnowledgeSearchRouter,
    RuleBasedQueryRouter,
)


def route_enabled(decision: object, modality: str) -> bool:
    routes = getattr(decision, "routes")
    return any(route.modality == modality and route.enabled for route in routes)


def test_date_query_routes_to_text_and_table() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("XX 项目的交付日期是什么？")

    assert route_enabled(decision, "text")
    assert route_enabled(decision, "table")
    assert not route_enabled(decision, "image")
    assert decision.intent == "fact_qa"


def test_image_query_routes_to_image_and_text() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("找一下支付系统架构图")

    assert route_enabled(decision, "text")
    assert route_enabled(decision, "image")
    assert decision.search_image_vector is True
    assert decision.answer_policy.must_return_visual is True
    assert decision.intent == "visual_lookup"
    assert decision.visual_result_mode == "single"


def test_gallery_image_query_uses_gallery_visual_mode() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("查找关于支付系统的全部图")

    assert route_enabled(decision, "image")
    assert decision.search_image_vector is True
    assert decision.visual_result_mode == "gallery"


def test_multimodal_query_routes_to_text_and_image() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("把风控流程相关的说明和流程图都找出来")

    assert route_enabled(decision, "text")
    assert route_enabled(decision, "image")
    assert decision.search_image_vector is True
    assert decision.intent == "multimodal_lookup"
    assert decision.answer_policy.must_return_visual is True


def test_doc_lookup_routes_to_metadata() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("哪些文件提到了验收日期？")

    assert route_enabled(decision, "metadata")
    assert route_enabled(decision, "text")
    assert route_enabled(decision, "table")
    assert not route_enabled(decision, "image")
    assert decision.search_image_vector is False
    assert decision.intent == "doc_lookup"


def test_default_query_routes_to_text_and_table_only() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("这个项目怎么样？")

    assert route_enabled(decision, "text")
    assert route_enabled(decision, "table")
    assert not route_enabled(decision, "image")
    assert not route_enabled(decision, "metadata")
    assert [route.modality for route in decision.routes] == [
        "text",
        "table",
        "image",
        "metadata",
    ]


def test_route_decision_json_dump_is_stable() -> None:
    router = RuleBasedQueryRouter()

    body = router.route("XX 的预算金额是多少？").model_dump(mode="json")

    assert body["query"] == "XX 的预算金额是多少？"
    assert body["intent"] == "fact_qa"
    assert body["search_image_vector"] is False
    assert len(body["routes"]) == 4
    table_route = next(route for route in body["routes"] if route["modality"] == "table")
    assert table_route["enabled"] is True
    assert table_route["weight"] == 1.3


def test_llm_router_prompt_requires_strict_json() -> None:
    prompt = LLMQueryRouter().build_prompt("找一下流程图")

    assert "输出严格 JSON" in prompt
    assert "不要输出解释文本" in prompt
    assert "找一下流程图" in prompt
    assert "search_image_vector" in prompt


def test_llm_router_uses_model_json_and_normalizes_image_route(
    monkeypatch: MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("INTENT_RECOGNITION_API_BASE_URL", "https://intent.example/v1")
    monkeypatch.setenv("INTENT_RECOGNITION_API_KEY", "intent-key")
    monkeypatch.setenv("INTENT_RECOGNITION_MODEL", "intent-router-model")
    monkeypatch.setenv("INTENT_RECOGNITION_TEMPERATURE", "0.1")
    monkeypatch.setenv("INTENT_RECOGNITION_MAX_TOKENS", "512")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "query": "系统架构怎么工作",
                                    "intent": "fact_qa",
                                    "search_image_vector": False,
                                    "routes": [
                                        {
                                            "modality": "text",
                                            "enabled": True,
                                            "weight": 1.0,
                                            "top_k": 30,
                                        },
                                        {
                                            "modality": "table",
                                            "enabled": True,
                                            "weight": 1.0,
                                            "top_k": 30,
                                        },
                                        {
                                            "modality": "image",
                                            "enabled": True,
                                            "weight": 1.4,
                                            "top_k": 10,
                                        },
                                        {
                                            "modality": "metadata",
                                            "enabled": False,
                                            "weight": 0.5,
                                            "top_k": 10,
                                        },
                                    ],
                                    "answer_policy": {
                                        "must_return_visual": False,
                                        "must_cite_source": True,
                                        "allow_no_answer": True,
                                    },
                                    "confidence": 0.91,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    try:
        decision = LLMQueryRouter(transport=httpx.MockTransport(handler)).route(
            "系统架构怎么工作"
        )
    finally:
        get_settings.cache_clear()

    assert decision.search_image_vector is False
    assert not route_enabled(decision, "image")
    assert decision.answer_policy.must_return_visual is False
    assert captured["url"] == "https://intent.example/v1/chat/completions"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "intent-router-model"
    assert payload["temperature"] == 0.1
    assert payload["max_tokens"] == 512
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"] == "Bearer intent-key"


def test_llm_router_enables_images_when_model_requests_image_vector(
    monkeypatch: MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("INTENT_RECOGNITION_API_BASE_URL", "https://intent.example/v1")
    monkeypatch.setenv("INTENT_RECOGNITION_MODEL", "intent-router-model")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "query": "找一下系统架构图",
                                    "intent": "visual_lookup",
                                    "search_image_vector": True,
                                    "routes": [
                                        {
                                            "modality": "text",
                                            "enabled": True,
                                            "weight": 1.0,
                                            "top_k": 30,
                                        },
                                        {
                                            "modality": "image",
                                            "enabled": False,
                                            "weight": 0.2,
                                            "top_k": 10,
                                        },
                                    ],
                                    "answer_policy": {
                                        "must_return_visual": False,
                                        "must_cite_source": True,
                                        "allow_no_answer": True,
                                    },
                                    "confidence": 0.95,
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    try:
        decision = LLMQueryRouter(transport=httpx.MockTransport(handler)).route(
            "找一下系统架构图"
        )
    finally:
        get_settings.cache_clear()

    assert decision.search_image_vector is True
    assert route_enabled(decision, "image")
    assert decision.answer_policy.must_return_visual is True


def test_llm_router_falls_back_to_rules_on_invalid_json(monkeypatch: MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("INTENT_RECOGNITION_API_BASE_URL", "https://intent.example/v1")
    monkeypatch.setenv("INTENT_RECOGNITION_MODEL", "intent-router-model")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    try:
        decision = LLMQueryRouter(transport=httpx.MockTransport(handler)).route("找一下流程图")
    finally:
        get_settings.cache_clear()

    assert decision.intent == "multimodal_lookup"
    assert decision.search_image_vector is True
    assert route_enabled(decision, "image")


def test_rule_based_knowledge_search_router_returns_profile_answer_for_identity() -> None:
    decision = RuleBasedKnowledgeSearchRouter().decide("你是谁？")

    assert decision.research_base is False
    assert decision.category == "identity"
    assert "知识库问答助手" in (decision.direct_answer or "")


def test_rule_based_knowledge_search_router_keeps_business_question_searchable() -> None:
    decision = RuleBasedKnowledgeSearchRouter().decide("公司的报销流程是什么？")

    assert decision.research_base is True
    assert decision.category == "normal_rag"


def test_rule_based_knowledge_search_router_does_not_overall_scope_only_question() -> None:
    decision = RuleBasedKnowledgeSearchRouter().decide("这个知识库里的消防制度是什么？")

    assert decision.research_base is True
    assert decision.category == "normal_rag"


def test_rule_based_knowledge_search_router_routes_overall_question() -> None:
    decision = RuleBasedKnowledgeSearchRouter().decide("当前知识库都包含什么数据？")

    assert decision.research_base is False
    assert decision.category == "knowledge_base_overall"

    summary_decision = RuleBasedKnowledgeSearchRouter().decide("这个知识库讲什么的？")
    assert summary_decision.research_base is False
    assert summary_decision.category == "knowledge_base_overall"


def test_rule_based_knowledge_search_router_routes_mixed_question() -> None:
    decision = RuleBasedKnowledgeSearchRouter().decide(
        "先说这个知识库有哪些资料，然后总结消防相关内容"
    )

    assert decision.research_base is True
    assert decision.category == "mixed"


def test_llm_knowledge_search_router_uses_classifier_false(monkeypatch: MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_API_BASE_URL", "https://intent.example/v1")
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_API_KEY", "classifier-key")
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_MODEL", "qwen3.6-flash")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "category=llm_direct"}}]},
        )

    try:
        decision = LLMKnowledgeSearchRouter(transport=httpx.MockTransport(handler)).decide(
            "随便聊聊"
        )
    finally:
        get_settings.cache_clear()

    assert decision.research_base is False
    assert decision.category == "llm_direct"
    assert captured["url"] == "https://intent.example/v1/chat/completions"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == "qwen3.6-flash"
    assert payload["max_tokens"] == 32
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["authorization"] == "Bearer classifier-key"


def test_llm_knowledge_search_router_uses_classifier_normal_rag(
    monkeypatch: MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_API_BASE_URL", "https://intent.example/v1")
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_MODEL", "qwen3.6-flash")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "category=normal_rag"}}]},
        )

    try:
        decision = LLMKnowledgeSearchRouter(transport=httpx.MockTransport(handler)).decide(
            "公司的报销制度是什么？"
        )
    finally:
        get_settings.cache_clear()

    assert decision.research_base is True
    assert decision.category == "normal_rag"


def test_llm_knowledge_search_router_uses_classifier_mixed(monkeypatch: MonkeyPatch) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_API_BASE_URL", "https://intent.example/v1")
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_MODEL", "qwen3.6-flash")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "category=mixed"}}]},
        )

    try:
        decision = LLMKnowledgeSearchRouter(transport=httpx.MockTransport(handler)).decide(
            "这个知识库有哪些资料，并总结消防相关内容"
        )
    finally:
        get_settings.cache_clear()

    assert decision.research_base is True
    assert decision.category == "mixed"


def test_llm_knowledge_search_router_falls_back_to_search_on_invalid_output(
    monkeypatch: MonkeyPatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_API_BASE_URL", "https://intent.example/v1")
    monkeypatch.setenv("KNOWLEDGE_SEARCH_CLASSIFIER_MODEL", "qwen3.6-flash")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "maybe"}}]})

    try:
        decision = LLMKnowledgeSearchRouter(transport=httpx.MockTransport(handler)).decide(
            "这个问题要不要查？"
        )
    finally:
        get_settings.cache_clear()

    assert decision.research_base is True
    assert decision.reason == "classifier_failed"
