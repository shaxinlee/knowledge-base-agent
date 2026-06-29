import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
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
    thinking: str | None = None


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
    ) -> Iterator[tuple[str, str]]: ...

    def generate_direct_answer(self, *, query: str, enable_thinking: bool = False) -> LLMAnswer: ...

    def stream_direct_answer(
        self, *, query: str, enable_thinking: bool = False
    ) -> Iterator[tuple[str, str]]: ...


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
        clean_content, thinking = strip_thinking_from_content(content)
        return LLMAnswer(
            content=clean_content,
            model=self.model,
            prompt_version=self.prompt_version,
            raw_prompt_snapshot=json.dumps(messages, ensure_ascii=False),
            token_usage=parse_token_usage(response_payload),
            thinking=thinking,
        )

    def stream_answer(
        self,
        *,
        query: str,
        contexts: Sequence[RetrievalResultItem],
        enable_thinking: bool = False,
    ) -> Iterator[tuple[str, str]]:
        messages = build_messages(query=query, contexts=contexts)
        payload = build_chat_completion_payload(
            model=self.model,
            messages=messages,
            stream=True,
            enable_thinking=enable_thinking,
        )
        thinking_filter = _ThinkingStreamFilter()
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
                        event = parse_sse_token(line)
                        if not event:
                            continue
                        reasoning = event.get("reasoning")
                        if reasoning:
                            yield ("thinking", reasoning)
                        content = event.get("content")
                        if content:
                            for kind, text in thinking_filter.feed(content):
                                yield (kind, text)
            for kind, text in thinking_filter.flush():
                yield (kind, text)
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
        clean_content, thinking = strip_thinking_from_content(content)
        return LLMAnswer(
            content=clean_content,
            model=self.model,
            prompt_version=DIRECT_PROMPT_VERSION,
            raw_prompt_snapshot=json.dumps(messages, ensure_ascii=False),
            token_usage=parse_token_usage(response_payload),
            thinking=thinking,
        )

    def stream_direct_answer(
        self, *, query: str, enable_thinking: bool = False
    ) -> Iterator[tuple[str, str]]:
        messages = build_direct_messages(query=query)
        payload = build_chat_completion_payload(
            model=self.model,
            messages=messages,
            stream=True,
            enable_thinking=enable_thinking,
        )
        thinking_filter = _ThinkingStreamFilter()
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
                        event = parse_sse_token(line)
                        if not event:
                            continue
                        reasoning = event.get("reasoning")
                        if reasoning:
                            yield ("thinking", reasoning)
                        content = event.get("content")
                        if content:
                            for kind, text in thinking_filter.feed(content):
                                yield (kind, text)
            for kind, text in thinking_filter.flush():
                yield (kind, text)
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="LLM API stream request failed.",
                status_code=502,
                details={"service": "llm-api", "error": str(exc)},
            ) from exc


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
    ) -> Iterator[tuple[str, str]]:
        answer = self.generate_answer(
            query=query,
            contexts=contexts,
            enable_thinking=enable_thinking,
        )
        for index in range(0, len(answer.content), 16):
            yield ("content", answer.content[index : index + 16])

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

    def stream_direct_answer(self, *, query: str, enable_thinking: bool = False) -> Iterator[tuple[str, str]]:
        answer = self.generate_direct_answer(query=query, enable_thinking=enable_thinking)
        for index in range(0, len(answer.content), 16):
            yield ("content", answer.content[index : index + 16])


def build_messages(*, query: str, contexts: Sequence[RetrievalResultItem]) -> list[dict[str, str]]:
    system_prompt = (
        "你是一个知识库问答助手。只能基于提供的上下文回答问题。"
        "如果上下文信息不足以回答问题，请回复：'当前知识库中没有找到足够依据回答该问题。'"
        "禁止使用上下文中没有出现过的事实或数字。"
        "每个事实陈述必须标注引用编号，格式如 [1]、[2]。"
        "引用编号必须与上下文中 [N] 的 N 完全一致，不允许跳号或错配。"
        "不要输出文件路径、图片 URL、资源路径、存储路径、文件名、页码、原始来源位置、"
        "原始 HTML 标签或原始 LaTeX 代码。将表格以可读表格形式呈现，"
        "公式以普通数学文本形式呈现。"
        "禁止在回复中使用'根据提供的上下文'、'根据上下文'、'根据检索到的信息'、"
        "'提供的信息'、'检索到的内容'等表述，直接回答问题即可。"
    )
    context_lines = []
    for index, context in enumerate(contexts, start=1):
        context_lines.append(
            f'<context id="{index}">\n'
            f"文件：{context.file_name}\n"
            f"定位：{context.source_locator}\n"
            f"内容：{normalize_special_elements(strip_visible_image_references(context.excerpt))}\n"
            f"</context>"
        )
    user_prompt = (
        "以下是检索到的相关上下文：\n\n"
        + "\n\n".join(context_lines)
        + "\n\n问题：\n"
        + query
        + "\n\n请先列出相关引用编号，再基于上下文组织回答，并标注引用编号。"
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


def parse_sse_token(line: str) -> dict[str, str | None] | None:
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
    if not isinstance(delta, dict):
        return None
    content = delta.get("content")
    reasoning = delta.get("reasoning_content")
    if reasoning is None:
        reasoning = delta.get("reasoning")
    if not isinstance(content, str):
        content = None
    if not isinstance(reasoning, str):
        reasoning = None
    if content is None and reasoning is None:
        return None
    return {"content": content, "reasoning": reasoning}


def invalid_llm_response() -> ApiError:
    return ApiError(
        code="UPSTREAM_SERVICE_ERROR",
        message="LLM API returned an unsupported response shape.",
        status_code=502,
        details={"service": "llm-api"},
    )


_THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL)


def strip_thinking_from_content(content: str) -> tuple[str, str | None]:
    """Strip thinking content embedded in model response content.

    Handles two patterns:
    1. <think>...</think> tags (common with Qwen3 models)
    2. "Here's a thinking process:" followed by content ending with </think>

    Returns (clean_content, thinking_content_or_None).
    """
    if not content:
        return content, None

    match = _THINK_TAG_RE.search(content)
    if match:
        thinking = match.group(1).strip() or None
        clean = (content[: match.start()] + content[match.end() :]).strip()
        return clean, thinking

    here_marker = "Here's a thinking process:"
    if here_marker in content and "</think>" in content:
        end_pos = content.index("</think>") + len("</think>")
        thinking = content[content.index(here_marker) : end_pos].strip()
        clean = content[end_pos:].strip()
        return clean, thinking

    return content, None


class _ThinkingStreamFilter:
    """Stateful filter that extracts thinking content from streamed content tokens.

    When a model puts thinking into the content field instead of the reasoning field,
    this filter detects thinking markers and routes tokens to the correct channel.
    """

    _THINK_OPEN = "<think>"
    _THINK_CLOSE = "</think>"
    _HERE_MARKER = "Here's a thinking process:"

    def __init__(self) -> None:
        self._buffer = ""
        self._in_thinking = False
        self._thinking_done = False
        self._here_detected = False

    def feed(self, token: str) -> list[tuple[str, str]]:
        """Feed a content token and return a list of (kind, text) events."""
        self._buffer += token
        events: list[tuple[str, str]] = []

        while self._buffer:
            if self._in_thinking:
                close_idx = self._buffer.find(self._THINK_CLOSE)
                if close_idx >= 0:
                    thinking_text = self._buffer[:close_idx]
                    if thinking_text:
                        events.append(("thinking", thinking_text))
                    self._buffer = self._buffer[close_idx + len(self._THINK_CLOSE) :]
                    self._in_thinking = False
                    self._thinking_done = True
                else:
                    safe = self._buffer[: -len(self._THINK_CLOSE)]
                    if safe:
                        events.append(("thinking", safe))
                        self._buffer = self._buffer[len(safe) :]
                    break
            else:
                open_idx = self._buffer.find(self._THINK_OPEN)
                here_idx = self._buffer.find(self._HERE_MARKER)

                if open_idx >= 0:
                    if open_idx > 0:
                        events.append(("content", self._buffer[:open_idx]))
                    self._buffer = self._buffer[open_idx + len(self._THINK_OPEN) :]
                    self._in_thinking = True
                elif here_idx >= 0:
                    if here_idx > 0:
                        events.append(("content", self._buffer[:here_idx]))
                    self._buffer = self._buffer[here_idx:]
                    self._in_thinking = True
                    self._here_detected = True
                elif self._thinking_done:
                    events.append(("content", self._buffer))
                    self._buffer = ""
                    break
                else:
                    # Only hold back suffix that could be a prefix of a thinking marker
                    markers = (self._THINK_OPEN, self._HERE_MARKER)
                    max_len = max(len(m) for m in markers)
                    hold_back = 0
                    for length in range(1, min(len(self._buffer), max_len) + 1):
                        suffix = self._buffer[-length:]
                        if any(m.startswith(suffix) for m in markers):
                            hold_back = length
                    if hold_back > 0:
                        safe = self._buffer[:-hold_back]
                        if safe:
                            events.append(("content", safe))
                        self._buffer = self._buffer[-hold_back:]
                    else:
                        events.append(("content", self._buffer))
                        self._buffer = ""
                    break

        return events

    def flush(self) -> list[tuple[str, str]]:
        """Flush remaining buffer at stream end."""
        events: list[tuple[str, str]] = []
        if self._in_thinking and self._buffer:
            events.append(("thinking", self._buffer))
        elif self._buffer:
            events.append(("content", self._buffer))
        self._buffer = ""
        return events


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
