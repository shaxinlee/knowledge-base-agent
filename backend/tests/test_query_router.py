from app.rag.query_router import LLMQueryRouter, RuleBasedQueryRouter


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
    assert decision.answer_policy.must_return_visual is True
    assert decision.intent == "visual_lookup"


def test_multimodal_query_routes_to_text_and_image() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("把风控流程相关的说明和流程图都找出来")

    assert route_enabled(decision, "text")
    assert route_enabled(decision, "image")
    assert decision.intent == "multimodal_lookup"
    assert decision.answer_policy.must_return_visual is True


def test_doc_lookup_routes_to_metadata() -> None:
    router = RuleBasedQueryRouter()

    decision = router.route("哪些文件提到了验收日期？")

    assert route_enabled(decision, "metadata")
    assert route_enabled(decision, "text")
    assert route_enabled(decision, "table")
    assert route_enabled(decision, "image")
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
    assert len(body["routes"]) == 4
    table_route = next(route for route in body["routes"] if route["modality"] == "table")
    assert table_route["enabled"] is True
    assert table_route["weight"] == 1.3


def test_llm_router_prompt_requires_strict_json() -> None:
    prompt = LLMQueryRouter().build_prompt("找一下流程图")

    assert "输出严格 JSON" in prompt
    assert "不要输出解释文本" in prompt
    assert "找一下流程图" in prompt
