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
VisualResultMode = Literal["none", "single", "gallery"]
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

VISUAL_GALLERY_KEYWORDS = (
    "全部图",
    "所有图",
    "相关图",
    "相关图片",
    "相似图",
    "相似图片",
    "相似",
    "找图",
    "图片列表",
    "图集",
    "all images",
    "similar image",
    "similar images",
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
    visual_result_mode: VisualResultMode = "none"
    routes: list[RouteItem]
    answer_policy: AnswerPolicy
    confidence: float = Field(ge=0, le=1)

    def normalized(self) -> "RouteDecision":
        return normalize_route_decision(self)


class QueryRouterProtocol(Protocol):
    def route(self, query: str) -> RouteDecision: ...


class KnowledgeSearchDecision(BaseModel):
    research_base: bool
    category: str = "knowledge_base"
    reason: str = ""
    direct_answer: str | None = None


class KnowledgeSearchRouterProtocol(Protocol):
    def decide(self, query: str) -> KnowledgeSearchDecision: ...


class RuleBasedKnowledgeSearchRouter:
    patterns: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "identity",
            (
                r"^(你|您|助手|这个助手|系统)?(是)?谁[？?。！!]*$",
                r"^(你|您)(叫)?(什么|啥)(名字)?[？?。！!]*$",
                r"^(介绍一下)?(你自己|自己)[？?。！!]*$",
            ),
        ),
        (
            "capability",
            (
                r"^(你|您)?(能|可以|会)(干什么|做什么|帮我做什么|提供什么帮助)[？?。！!]*$",
                r"^(你|您)有什么(能力|功能)[？?。！!]*$",
            ),
        ),
        (
            "greeting",
            (
                r"^(你好|您好|哈喽|嗨|hi|hello|hey)[。！!？?\s]*$",
                r"^(早上好|上午好|下午好|晚上好)[。！!？?\s]*$",
            ),
        ),
        (
            "thanks",
            (
                r"^(谢谢|感谢|多谢|辛苦了|thank you|thanks)[。！!？?\s]*$",
                r"^(谢谢你|感谢你|多谢你)[。！!？?\s]*$",
            ),
        ),
        (
            "usage",
            (
                r"^(怎么用|如何使用|使用说明|帮助|help)[。！!？?\s]*$",
                r"^(怎么使用|如何使用)(你|这个系统|知识库助手)[？?。！!]*$",
            ),
        ),
        (
            "handoff",
            (
                r"^(转人工|人工客服|联系人工|我要人工|找人工)[。！!？?\s]*$",
                r"^(帮我)?(转接|联系)(人工|客服|人工客服)[。！!？?\s]*$",
            ),
        ),
        (
            "casual",
            (
                r"^(陪我聊聊天|聊聊天|讲个笑话|说个笑话)[。！!？?\s]*$",
                r"^(你真棒|你不错|你好吗)[。！!？?\s]*$",
            ),
        ),
    )

    def decide(self, query: str) -> KnowledgeSearchDecision:
        normalized_query = normalize_query_for_rule_matching(query)
        if not normalized_query:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Query cannot be empty.",
                status_code=422,
            )
        for category, patterns in self.patterns:
            if any(re.search(pattern, normalized_query, flags=re.IGNORECASE) for pattern in patterns):
                from app.services.assistant_profile import get_profile_answer

                return KnowledgeSearchDecision(
                    research_base=False,
                    category=category,
                    reason="rule_matched",
                    direct_answer=get_profile_answer(category),
                )
        return KnowledgeSearchDecision(
            research_base=True,
            category="knowledge_base",
            reason="rule_not_matched",
        )


class LLMKnowledgeSearchRouter:
    prompt_template = """你是一个知识库问答系统的路由器。
请判断用户问题是否需要检索知识库。

如果问题是以下类型，不需要检索：
- 询问助手身份
- 询问助手能力
- 寒暄
- 感谢
- 使用说明
- 转人工客服
- 明显闲聊

如果问题涉及公司制度、产品文档、流程、业务知识、FAQ，则需要检索知识库。

请输出布尔类型数据：
research_base=true 或者research_base=false

用户问题：{query}
"""

    def __init__(self, *, transport: httpx.BaseTransport | None = None) -> None:
        self.transport = transport
        self.rule_router = RuleBasedKnowledgeSearchRouter()

    def build_prompt(self, query: str) -> str:
        return self.prompt_template.format(query=query)

    def decide(self, query: str) -> KnowledgeSearchDecision:
        normalized_query = query.strip()
        if not normalized_query:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Query cannot be empty.",
                status_code=422,
            )

        rule_decision = self.rule_router.decide(normalized_query)
        if not rule_decision.research_base:
            return rule_decision

        settings = get_settings()
        base_url = (
            settings.knowledge_search_classifier_api_base_url.strip()
            or settings.intent_recognition_api_base_url.strip()
            or settings.llm_api_base_url.strip()
            or settings.llm_api_base.strip()
        )
        api_key = (
            settings.knowledge_search_classifier_api_key
            or settings.intent_recognition_api_key
            or settings.llm_api_key
        )
        model = settings.knowledge_search_classifier_model.strip() or "qwen3.6-flash"
        if not base_url or not model:
            return KnowledgeSearchDecision(
                research_base=True,
                category="knowledge_base",
                reason="classifier_not_configured",
            )

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是知识库检索前置分类器。你只能输出 "
                        "research_base=true 或 research_base=false。"
                    ),
                },
                {"role": "user", "content": self.build_prompt(normalized_query)},
            ],
            "stream": False,
            "temperature": settings.knowledge_search_classifier_temperature,
            "max_tokens": settings.knowledge_search_classifier_max_tokens,
        }
        try:
            with httpx.Client(
                timeout=settings.knowledge_search_classifier_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    build_chat_completions_url(base_url),
                    headers=build_llm_headers(api_key),
                    json=payload,
                )
                response.raise_for_status()
            research_base = parse_research_base_output(
                parse_chat_completion_content(response.json())
            )
            return KnowledgeSearchDecision(
                research_base=research_base,
                category="knowledge_base" if research_base else "llm_direct",
                reason="classifier",
            )
        except (httpx.HTTPError, ValueError, ApiError):
            return KnowledgeSearchDecision(
                research_base=True,
                category="knowledge_base",
                reason="classifier_failed",
            )


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
        gallery_hit = contains_any(normalized_query, VISUAL_GALLERY_KEYWORDS)

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
            top_k["image"] = 20
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
            visual_result_mode="gallery" if gallery_hit else "single" if must_return_visual else "none",
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
- 如果用户要求全部图、相关图片、相似图片、找图集，visual_result_mode=gallery；如果只是解释某张图，visual_result_mode=single。
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
                "visual_result_mode": "none | single | gallery",
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
        base_url = (
            settings.intent_recognition_api_base_url.strip()
            or settings.llm_api_base_url.strip()
            or settings.llm_api_base.strip()
        )
        api_key = settings.intent_recognition_api_key or settings.llm_api_key
        model = settings.intent_recognition_model.strip() or settings.llm_model.strip()
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
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "temperature": settings.intent_recognition_temperature,
            "max_tokens": settings.intent_recognition_max_tokens,
        }
        try:
            with httpx.Client(
                timeout=settings.intent_recognition_timeout_seconds,
                transport=self.transport,
            ) as client:
                response = client.post(
                    build_chat_completions_url(base_url),
                    headers=build_llm_headers(api_key),
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


def get_knowledge_search_router() -> KnowledgeSearchRouterProtocol:
    return LLMKnowledgeSearchRouter()


def normalize_query_for_rule_matching(query: str) -> str:
    return re.sub(r"\s+", "", query.strip().lower())


def parse_research_base_output(content: str) -> bool:
    normalized = content.strip().lower()
    normalized = re.sub(r"^```(?:text)?\s*", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\s*```$", "", normalized)
    true_match = re.search(r"research_base\s*=\s*true", normalized)
    false_match = re.search(r"research_base\s*=\s*false", normalized)
    if true_match and not false_match:
        return True
    if false_match and not true_match:
        return False
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ValueError("Classifier output must contain research_base=true or research_base=false.")


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
    visual_result_mode = decision.visual_result_mode
    if search_image_vector and visual_result_mode == "none":
        visual_result_mode = (
            "gallery" if contains_any(decision.query, VISUAL_GALLERY_KEYWORDS) else "single"
        )
    if not search_image_vector:
        visual_result_mode = "none"
    return decision.model_copy(
        update={
            "search_image_vector": search_image_vector,
            "visual_result_mode": visual_result_mode,
            "routes": normalized_routes,
            "answer_policy": answer_policy,
        }
    )


def contains_any(query: str, keywords: tuple[str, ...]) -> bool:
    lowered = query.lower()
    return any(re.search(re.escape(keyword.lower()), lowered) for keyword in keywords)
