import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.retrieval import RetrievalResultItem
from app.services.content_normalization import normalize_special_elements
from app.services.model_settings import get_model_settings
from app.services.visual_citations import strip_visible_image_references

PROMPT_VERSION = "rag-citations-v1"
DEMO_PROMPT_VERSION = "template-demo-v1"
DIRECT_PROMPT_VERSION = "direct-chat-v1"


@dataclass(frozen=True)
class LLMAnswer:
    content: str
    model: str
    prompt_version: str
    raw_prompt_snapshot: str
    token_usage: dict[str, Any]


class LLMClientProtocol(Protocol):
    model: str
    prompt_version: str

    def generate_answer(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievalResultItem],
        enable_thinking: bool = False,
    ) -> LLMAnswer: ...

    def stream_answer(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievalResultItem],
        enable_thinking: bool = False,
    ) -> Iterator[str]: ...

    def generate_direct_answer(self, *, query: str, enable_thinking: bool = False) -> LLMAnswer: ...

    def stream_direct_answer(
        self, *, query: str, enable_thinking: bool = False
    ) -> Iterator[str]: ...


class LLMApiClient:
    prompt_version = PROMPT_VERSION

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 120,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def generate_answer(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievalResultItem],
        enable_thinking: bool = False,
    ) -> LLMAnswer:
        messages = build_messages(query=query, contexts=contexts)
        payload = build_chat_completion_payload(
            model=self.model,
            messages=messages,
            stream=False,
            enable_thinking=enable_thinking,
        )
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    build_chat_completions_url(self.base_url),
                    headers=build_llm_headers(self.api_key),
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="LLM API request failed.",
                status_code=502,
                details={"service": "llm-api", "error": str(exc)},
            ) from exc
        response_payload = response.json()
        content = parse_chat_completion_content(response_payload)
        return LLMAnswer(
            content=content,
            model=self.model,
            prompt_version=self.prompt_version,
            raw_prompt_snapshot=json.dumps(messages, ensure_ascii=False),
            token_usage=parse_token_usage(response_payload),
        )

    def stream_answer(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievalResultItem],
        enable_thinking: bool = False,
    ) -> Iterator[str]:
        messages = build_messages(query=query, contexts=contexts)
        payload = build_chat_completion_payload(
            model=self.model,
            messages=messages,
            stream=True,
            enable_thinking=enable_thinking,
        )
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                with client.stream(
                    "POST",
                    build_chat_completions_url(self.base_url),
                    headers=build_llm_headers(self.api_key),
                    json=payload,
                ) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        token = parse_sse_token(line)
                        if token:
                            yield token
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="LLM API stream request failed.",
                status_code=502,
                details={"service": "llm-api", "error": str(exc)},
            ) from exc

    def generate_direct_answer(self, *, query: str, enable_thinking: bool = False) -> LLMAnswer:
        messages = build_direct_messages(query=query)
        payload = build_chat_completion_payload(
            model=self.model,
            messages=messages,
            stream=False,
            enable_thinking=enable_thinking,
        )
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    build_chat_completions_url(self.base_url),
                    headers=build_llm_headers(self.api_key),
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="LLM API request failed.",
                status_code=502,
                details={"service": "llm-api", "error": str(exc)},
            ) from exc
        response_payload = response.json()
        content = parse_chat_completion_content(response_payload)
        return LLMAnswer(
            content=content,
            model=self.model,
            prompt_version=DIRECT_PROMPT_VERSION,
            raw_prompt_snapshot=json.dumps(messages, ensure_ascii=False),
            token_usage=parse_token_usage(response_payload),
        )

    def stream_direct_answer(self, *, query: str, enable_thinking: bool = False) -> Iterator[str]:
        answer = self.generate_direct_answer(query=query, enable_thinking=enable_thinking)
        for index in range(0, len(answer.content), 16):
            yield answer.content[index : index + 16]


class TemplateDemoLLMClient:
    model = "template-demo"
    prompt_version = DEMO_PROMPT_VERSION

    def generate_answer(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievalResultItem],
        enable_thinking: bool = False,
    ) -> LLMAnswer:
        content = build_template_answer(query=query, contexts=contexts)
        return LLMAnswer(
            content=content,
            model=self.model,
            prompt_version=self.prompt_version,
            raw_prompt_snapshot=json.dumps(
                build_messages(query=query, contexts=contexts),
                ensure_ascii=False,
            ),
            token_usage={},
        )

    def stream_answer(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievalResultItem],
        enable_thinking: bool = False,
    ) -> Iterator[str]:
        answer = self.generate_answer(
            query=query,
            contexts=contexts,
            enable_thinking=enable_thinking,
        )
        for index in range(0, len(answer.content), 16):
            yield answer.content[index : index + 16]

    def generate_direct_answer(self, *, query: str, enable_thinking: bool = False) -> LLMAnswer:
        messages = build_direct_messages(query=query)
        content = "你好，我是知识库问答助手。你可以直接提问需要查询的知识库内容。"
        return LLMAnswer(
            content=content,
            model=self.model,
            prompt_version=DIRECT_PROMPT_VERSION,
            raw_prompt_snapshot=json.dumps(messages, ensure_ascii=False),
            token_usage={},
        )

    def stream_direct_answer(self, *, query: str, enable_thinking: bool = False) -> Iterator[str]:
        answer = self.generate_direct_answer(query=query, enable_thinking=enable_thinking)
        for index in range(0, len(answer.content), 16):
            yield answer.content[index : index + 16]


def build_messages(*, query: str, contexts: Sequence[RetrievalResultItem]) -> list[dict[str, str]]:
    system_prompt = (
        "你是一个知识库问答助手。只能基于提供的上下文回答问题。"
        "如果上下文信息不足以回答问题，请简要拒答。"
        "每个事实陈述必须标注引用编号，格式如 [1]、[2]。"
        "不要输出文件路径、图片 URL、资源路径、存储路径、文件名、页码、原始来源位置、"
        "原始 HTML 标签或原始 LaTeX 代码。将表格以可读表格形式呈现，"
        "公式以普通数学文本形式呈现。"
    )
    context_lines = []
    for index, context in enumerate(contexts, start=1):
        context_lines.append(
            "\n".join(
                [
                    f"[{index}]",
                    f"文件：{context.file_name}",
                    f"定位：{context.source_locator}",
                    f"内容：{normalize_special_elements(strip_visible_image_references(context.excerpt))}",
                ]
            )
        )
    user_prompt = (
        "上下文：\n"
        + "\n\n".join(context_lines)
        + "\n\n问题：\n"
        + query
        + "\n\n请基于上下文回答，并标注引用编号。"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_direct_messages(*, query: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是一个知识库问答助手。请直接回答对话或产品使用类问题，"
                "不需要引用知识库来源。如果用户询问的是业务事实、制度、产品文档、"
                "操作流程或 FAQ 内容，请引导用户在知识库中提问。"
            ),
        },
        {"role": "user", "content": query},
    ]


def build_chat_completion_payload(
    *,
    model: str,
    messages: Sequence[dict[str, str]],
    stream: bool,
    enable_thinking: bool,
    temperature: float = 0.5,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": list(messages),
        "stream": stream,
        "temperature": temperature,
        "enable_thinking": enable_thinking,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }


def build_template_answer(*, query: str, contexts: Sequence[RetrievalResultItem]) -> str:
    if not contexts:
        return build_refusal_answer()
    lines = ["根据当前知识库检索结果，回答如下："]
    for index, context in enumerate(contexts[:6], start=1):
        lines.append(
            f"[{index}] {normalize_special_elements(strip_visible_image_references(context.excerpt))}"
        )
    lines.append(f"以上内容用于回答：{query}")
    return "\n".join(lines)


def build_refusal_answer() -> str:
    return (
        "当前知识库中没有找到足够依据回答该问题。\n"
        "我没有检索到可引用的相关内容。这些内容不足以支持明确结论。"
        "建议补充包含该问题细节的文档后重新提问。"
    )


def build_chat_completions_url(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url}/chat/completions"


def build_llm_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def parse_chat_completion_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise invalid_llm_response()
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise invalid_llm_response()
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise invalid_llm_response()
    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    text = first_choice.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise invalid_llm_response()


def parse_token_usage(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and isinstance(payload.get("usage"), dict):
        return dict(payload["usage"])
    return {}


def parse_sse_token(line: str) -> str | None:
    if not line.startswith("data:"):
        return None
    data = line.removeprefix("data:").strip()
    if data == "[DONE]":
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    delta = first_choice.get("delta")
    content = delta.get("content") if isinstance(delta, dict) else None
    if isinstance(content, str):
        return content
    return None


def invalid_llm_response() -> ApiError:
    return ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="LLM API returned an unsupported response shape.",
        status_code=502,
        details={"service": "llm-api"},
    )


def get_llm_client() -> LLMClientProtocol:
    settings = get_settings()
    model_settings = get_model_settings().llm
    base_url = (
        model_settings.base_url.strip()
        or settings.llm_api_base_url.strip()
        or settings.llm_api_base.strip()
    )
    model = model_settings.model.strip() or settings.llm_model.strip()
    api_key = model_settings.api_key or settings.llm_api_key
    if base_url and model:
        return LLMApiClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    return TemplateDemoLLMClient()
