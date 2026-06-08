import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError
from app.schemas.retrieval import RetrievalResultItem

PROMPT_VERSION = "rag-citations-v1"
DEMO_PROMPT_VERSION = "template-demo-v1"


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
        self, *, query: str, contexts: Sequence[RetrievalResultItem]
    ) -> LLMAnswer: ...

    def stream_answer(
        self, *, query: str, contexts: Sequence[RetrievalResultItem]
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

    def generate_answer(self, *, query: str, contexts: Sequence[RetrievalResultItem]) -> LLMAnswer:
        messages = build_messages(query=query, contexts=contexts)
        payload = {"model": self.model, "messages": messages, "stream": False}
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
        self, *, query: str, contexts: Sequence[RetrievalResultItem]
    ) -> Iterator[str]:
        messages = build_messages(query=query, contexts=contexts)
        payload = {"model": self.model, "messages": messages, "stream": True}
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


class TemplateDemoLLMClient:
    model = "template-demo"
    prompt_version = DEMO_PROMPT_VERSION

    def generate_answer(self, *, query: str, contexts: Sequence[RetrievalResultItem]) -> LLMAnswer:
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
        self, *, query: str, contexts: Sequence[RetrievalResultItem]
    ) -> Iterator[str]:
        answer = self.generate_answer(query=query, contexts=contexts)
        for index in range(0, len(answer.content), 16):
            yield answer.content[index : index + 16]


def build_messages(*, query: str, contexts: Sequence[RetrievalResultItem]) -> list[dict[str, str]]:
    system_prompt = (
        "You are a knowledge base assistant. Answer only using the provided context. "
        "If the context is insufficient, refuse briefly. Every factual claim must cite "
        "the provided citation numbers like [1], [2]. Do not invent file names, pages, "
        "or source locations."
    )
    context_lines = []
    for index, context in enumerate(contexts, start=1):
        context_lines.append(
            "\n".join(
                [
                    f"[{index}]",
                    f"file: {context.file_name}",
                    f"source_locator: {context.source_locator}",
                    f"excerpt: {context.excerpt}",
                ]
            )
        )
    user_prompt = (
        "Context:\n"
        + "\n\n".join(context_lines)
        + "\n\nQuestion:\n"
        + query
        + "\n\nAnswer with citations."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def build_template_answer(*, query: str, contexts: Sequence[RetrievalResultItem]) -> str:
    if not contexts:
        return build_refusal_answer()
    lines = ["根据当前知识库检索结果，回答如下："]
    for index, context in enumerate(contexts[:6], start=1):
        lines.append(f"[{index}] {context.excerpt}")
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
    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
        return delta["content"]
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
    base_url = settings.llm_api_base_url.strip() or settings.llm_api_base.strip()
    if base_url and settings.llm_model.strip():
        return LLMApiClient(
            base_url=base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
        )
    return TemplateDemoLLMClient()
