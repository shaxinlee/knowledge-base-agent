import json
import re
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.errors import ApiError
from app.services.llm import (
    build_chat_completions_url,
    build_llm_headers,
    parse_chat_completion_content,
)

Modality = Literal["text", "table", "image", "metadata"]
Intent = Literal[
    "fact_qa",
    "visual_lookup",
    "table_lookup",
    "multimodal_lookup",
    "doc_lookup",
    "summarization",
    "comparison",
    "unknown",
]

MODALITIES: tuple[Modality, ...] = ("text", "table", "image", "metadata")

FIELD_KEYWORDS = (
    "日期",
    "时间",
    "什么时候",
    "金额",
    "多少钱",
    "数量",
    "比例",
    "状态",
    "负责人",
    "版本",
    "截止时间",
    "上线时间",
    "交付时间",
    "验收时间",
    "生效日期",
    "预算",
    "清单",
    "列表",
)
VISUAL_KEYWORDS = (
    "图",
    "图片",
    "截图",
    "照片",
    "插图",
    "示意图",
    "架构图",
    "流程图",
    "拓扑图",
    "甘特图",
    "柱状图",
    "折线图",
    "饼图",
    "曲线图",
    "图表",
    "页面",
    "界面",
    "设计稿",
    "diagram",
    "figure",
    "chart",
    "plot",
    "screenshot",
    "flowchart",
    "architecture diagram",
)
MULTIMODAL_KEYWORDS = (
    "说明",
    "设计",
    "流程",
    "总结",
    "包括图",
    "相关内容",
    "都找",
    "一起",
    "以及",
    "和文字",
)
DOC_LOOKUP_KEYWORDS = (
    "哪些文件",
    "哪个文件",
    "哪份文件",
    "哪些文档",
    "哪个文档",
    "哪份文档",
    "出现在哪些",
    "提到了",
    "来源",
    "上传时间",
    "最新版本",
    "文件名",
)


class RouteItem(BaseModel):
    modality: Modality
    enabled: bool
    weight: float = Field(ge=0)
    top_k: int = Field(ge=1)


class AnswerPolicy(BaseModel):
    must_return_visual: bool = False
    must_cite_source: bool = True
    allow_no_answer: bool = True


class RouteDecision(BaseModel):
    query: str
    intent: Intent
    search_image_vector: bool = False
    routes: list[RouteItem]
    answer_policy: AnswerPolicy
    confidence: float = Field(ge=0, le=1)

    def normalized(self) -> "RouteDecision":
        return normalize_route_decision(self)


class QueryRouterProtocol(Protocol):
    def route(self, query: str) -> RouteDecision: ...


class RuleBasedQueryRouter:
    def route(self, query: str) -> RouteDecision:
        normalized_query = query.strip()
        if not normalized_query:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Query cannot be empty.",
                status_code=422,
            )

        field_hit = contains_any(normalized_query, FIELD_KEYWORDS)
        visual_hit = contains_any(normalized_query, VISUAL_KEYWORDS)
        multimodal_hit = visual_hit and contains_any(normalized_query, MULTIMODAL_KEYWORDS)
        doc_lookup_hit = contains_any(normalized_query, DOC_LOOKUP_KEYWORDS)

        enabled: dict[Modality, bool] = {
            "text": True,
            "table": True,
            "image": False,
            "metadata": False,
        }
        weights: dict[Modality, float] = {
            "text": 1.0,
            "table": 1.0,
            "image": 0.2,
            "metadata": 0.5,
        }
        top_k: dict[Modality, int] = {
            "text": 30,
            "table": 30,
            "image": 10,
            "metadata": 10,
        }
        intent: Intent = "unknown"
        confidence = 0.55
        must_return_visual = False

        if field_hit:
            intent = "fact_qa"
            enabled["text"] = True
            enabled["table"] = True
            weights["table"] = 1.3
            confidence = 0.72

        if visual_hit:
            intent = "visual_lookup"
            enabled["text"] = True
            enabled["table"] = False
            enabled["image"] = True
            weights["image"] = 1.4
            must_return_visual = True
            confidence = 0.82

        if multimodal_hit:
            intent = "multimodal_lookup"
            enabled["text"] = True
            enabled["table"] = False
            enabled["image"] = True
            weights["image"] = 1.35
            must_return_visual = True
            confidence = 0.86

        if doc_lookup_hit:
            intent = "doc_lookup"
            enabled = {"text": True, "table": True, "image": True, "metadata": True}
            weights.update({"table": 1.2, "image": 0.8, "metadata": 1.1})
            must_return_visual = False
            confidence = 0.82

        routes = [
            RouteItem(
                modality=modality,
                enabled=enabled[modality],
                weight=weights[modality],
                top_k=top_k[modality],
            )
            for modality in MODALITIES
        ]
        return RouteDecision(
            query=normalized_query,
            intent=intent,
            search_image_vector=must_return_visual,
            routes=routes,
            answer_policy=AnswerPolicy(must_return_visual=must_return_visual),
            confidence=confidence,
        ).normalized()


class LLMQueryRouter:
    prompt_template = """你是知识库检索路由器。请判断用户问题需要从哪些内容类型中检索答案。

内容类型：
1. text：正文、段落、条款、说明。
2. table：表格、清单、排期、金额、日期、状态、负责人等结构化字段。
3. image：图片、图表、截图、架构图、流程图、页面图、示意图。
4. metadata：文件名、版本、作者、上传时间、文档级属性。

规则：
- 如果用户明确提到图、图片、截图、架构图、流程图、曲线图、柱状图、界面、UI，则 image=true。
- 只有用户明确想查看图片、截图、图表、架构图、流程图、页面图等视觉内容时，search_image_vector=true。
- 普通事实问答、总结、解释、查日期/金额/负责人/状态时，search_image_vector=false，即使相关文档里可能包含图片。
- 如果用户询问日期、金额、数量、状态、负责人、版本、清单、列表，应 table=true，同时 text=true。
- 如果用户询问条款、定义、说明、原因、流程、政策，应 text=true。
- 如果问题不明确，默认 text=true；对于事实型字段问题，同时 table=true。
- 不要只选一个，可以多选。
- 输出严格 JSON，不要输出解释文本。

用户问题：{query}

输出格式：
{schema}
"""

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self.transport = transport

    def build_prompt(self, query: str) -> str:
        schema = json.dumps(
            {
                "query": "...",
                "intent": (
                    "fact_qa | visual_lookup | table_lookup | multimodal_lookup | "
                    "doc_lookup | summarization | comparison | unknown"
                ),
                "search_image_vector": False,
                "routes": [
                    {"modality": "text", "enabled": True, "weight": 1.0, "top_k": 30},
                    {"modality": "table", "enabled": True, "weight": 1.0, "top_k": 30},
                    {"modality": "image", "enabled": False, "weight": 0.2, "top_k": 10},
                    {"modality": "metadata", "enabled": False, "weight": 0.5, "top_k": 10},
                ],
                "answer_policy": {
                    "must_return_visual": False,
                    "must_cite_source": True,
                    "allow_no_answer": True,
                },
                "confidence": 0.0,
            },
            ensure_ascii=False,
        )
        return self.prompt_template.format(query=query, schema=schema)

    def route(self, query: str) -> RouteDecision:
        normalized_query = query.strip()
        if not normalized_query:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Query cannot be empty.",
                status_code=422,
            )

        settings = get_settings()
        base_url = settings.llm_api_base_url.strip() or settings.llm_api_base.strip()
        model = settings.llm_model.strip()
        if not base_url or not model:
            return RuleBasedQueryRouter().route(normalized_query)

        messages = [
            {
                "role": "system",
                "content": (
                    "你是知识库检索路由器。你只能输出一个 JSON 对象，"
                    "不要输出 markdown、解释或额外文本。"
                ),
            },
            {"role": "user", "content": self.build_prompt(normalized_query)},
        ]
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            with httpx.Client(timeout=30, transport=self.transport) as client:
                response = client.post(
                    build_chat_completions_url(base_url),
                    headers=build_llm_headers(settings.llm_api_key),
                    json=payload,
                )
                response.raise_for_status()
            content = parse_chat_completion_content(response.json())
            return parse_route_decision(content, fallback_query=normalized_query)
        except (httpx.HTTPError, ValueError, ValidationError, ApiError):
            return RuleBasedQueryRouter().route(normalized_query)


def parse_route_decision(content: str, *, fallback_query: str) -> RouteDecision:
    payload = extract_json_object(content)
    if not isinstance(payload, dict):
        raise ValueError("Router output must be a JSON object.")
    payload["query"] = str(payload.get("query") or fallback_query).strip() or fallback_query
    return RouteDecision.model_validate(payload).normalized()


def extract_json_object(content: str) -> Any:
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise
        return json.loads(stripped[start : end + 1])


def get_query_router() -> QueryRouterProtocol:
    return LLMQueryRouter()


def route_enabled(routes: list[RouteItem], modality: Modality) -> bool:
    return any(route.modality == modality and route.enabled for route in routes)


def build_normalized_routes(
    routes: list[RouteItem],
    *,
    search_image_vector: bool,
) -> list[RouteItem]:
    routes_by_modality = {route.modality: route for route in routes}
    normalized_routes: list[RouteItem] = []
    defaults = {
        "text": RouteItem(modality="text", enabled=True, weight=1.0, top_k=30),
        "table": RouteItem(modality="table", enabled=True, weight=1.0, top_k=30),
        "image": RouteItem(modality="image", enabled=False, weight=0.2, top_k=10),
        "metadata": RouteItem(modality="metadata", enabled=False, weight=0.5, top_k=10),
    }
    for modality in MODALITIES:
        route = routes_by_modality.get(modality, defaults[modality])
        if modality == "image":
            route = route.model_copy(
                update={
                    "enabled": search_image_vector,
                    "weight": max(route.weight, 1.0) if search_image_vector else route.weight,
                }
            )
        normalized_routes.append(route)
    if not route_enabled(normalized_routes, "text"):
        normalized_routes[0] = normalized_routes[0].model_copy(update={"enabled": True})
    return normalized_routes


def normalize_route_decision(decision: RouteDecision) -> RouteDecision:
    search_image_vector = bool(decision.search_image_vector)
    if decision.answer_policy.must_return_visual:
        search_image_vector = True
    normalized_routes = build_normalized_routes(
        decision.routes,
        search_image_vector=search_image_vector,
    )
    answer_policy = decision.answer_policy.model_copy(
        update={"must_return_visual": search_image_vector}
    )
    return decision.model_copy(
        update={
            "search_image_vector": search_image_vector,
            "routes": normalized_routes,
            "answer_policy": answer_policy,
        }
    )


def contains_any(query: str, keywords: tuple[str, ...]) -> bool:
    lowered = query.lower()
    return any(re.search(re.escape(keyword.lower()), lowered) for keyword in keywords)
