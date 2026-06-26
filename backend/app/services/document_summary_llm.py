import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

import httpx
from pydantic import ValidationError

from app.core.config import Settings, get_settings
from app.schemas.document_summaries import ChunkKnowledgeExtractionPayload
from app.services.llm import build_chat_completions_url, build_llm_headers
from app.services.model_settings import get_model_settings

CHUNK_PROMPT_VERSION = "chunk-summary-v2"
DOCUMENT_PROMPT_VERSION = "document-summary-v1"
COMMUNITY_PROMPT_VERSION = "knowledge-base-community-summary-v1"

CHUNK_SYSTEM_PROMPT = """请用最简短的语句总结以下 Chunk 的核心内容。

要求：
1. 仅依据原文，不得使用外部知识。
2. 尽量简短，1~2 句话，不超过 80 个中文字符。
3. 若原文无实质信息，输出"无实质内容"。
4. 直接输出摘要文本，不要任何解释，不要 JSON，不要 Markdown。"""

OUTPUT_SCHEMA_TEXT = ""

DOCUMENT_SYSTEM_PROMPT = """你是一个通用文档摘要器。只能依据输入的 Chunk 短摘要生成整篇文档摘要，不得使用外部知识。

要求：
1. 概括文档的核心主题、事实、定义、规则、要求、流程、决定、结果、风险和限制。
2. 使用连贯的段落形式，不得列出条目或编号。
3. 保持信息完整，不得遗漏重要内容。
4. 不输出解释或额外说明。"""

COMMUNITY_SYSTEM_PROMPT = """你是知识库社区摘要生成器。请根据输入的多个文档短摘要，生成该社区/主题的概括性摘要。
使用 1~3 句连贯的中文，涵盖主要主题和核心信息。"""


@dataclass(frozen=True)
class ChunkPromptInput:
    chunk_id: str
    document_id: str
    section_path: str | None
    page_no: str | int | None
    content_type: str
    chunk_text: str


@dataclass(frozen=True)
class SummarySource:
    chunk_id: str
    section_path: str
    source_locator: str
    short_summary: str


class DocumentSummaryLLMError(Exception):
    def __init__(self, code: str, message: str, *, attempts: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.attempts = attempts


class DocumentSummaryLLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        settings: Settings,
        request_semaphore: asyncio.Semaphore,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.settings = settings
        self.request_semaphore = request_semaphore
        self._client = httpx.AsyncClient(
            timeout=settings.document_summary_timeout_seconds,
            transport=transport,
            limits=httpx.Limits(
                max_connections=settings.document_summary_http_max_connections,
                max_keepalive_connections=(
                    settings.document_summary_http_max_keepalive_connections
                ),
            ),
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def extract_chunk(
        self, prompt_input: ChunkPromptInput
    ) -> tuple[ChunkKnowledgeExtractionPayload, int]:
        messages = build_chunk_messages(prompt_input)
        attempts = 0
        try:
            content, used_attempts = await self._complete(
                messages=messages,
                max_tokens=self.settings.document_summary_chunk_max_tokens,
            )
            attempts += used_attempts
            return await asyncio.to_thread(
                validate_chunk_extraction, content, prompt_input
            ), attempts
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        f"上一条输出未通过校验。请仅返回修复后的完整 JSON，不要解释。"
                        f"校验错误：{str(exc)[:800]}"
                    ),
                },
            ]
            try:
                repaired, used_attempts = await self._complete(
                    messages=repair_messages,
                    max_tokens=self.settings.document_summary_chunk_max_tokens,
                )
                attempts += used_attempts
                return await asyncio.to_thread(
                    validate_chunk_extraction, repaired, prompt_input
                ), attempts
            except (json.JSONDecodeError, ValidationError, ValueError) as repair_exc:
                raise DocumentSummaryLLMError(
                    "INVALID_EXTRACTION_RESPONSE",
                    str(repair_exc)[:2000],
                    attempts=attempts,
                ) from repair_exc

    async def summarize_document(
        self, sources: Sequence[SummarySource]
    ) -> tuple[str, int]:
        return await self._summarize_sources(sources)

    async def summarize_community(
        self, sources: Sequence[SummarySource]
    ) -> tuple[str, int]:
        return await self._summarize_community_sources(sources)

    async def _summarize_sources(
        self,
        sources: Sequence[SummarySource],
        *,
        instruction: str = "请生成整篇文档的最终摘要。",
    ) -> tuple[str, int]:
        content, attempts = await self._complete(
            messages=build_document_messages(sources, instruction=instruction),
            max_tokens=self.settings.document_summary_final_max_tokens,
        )
        normalized = content.strip()
        if not normalized:
            raise DocumentSummaryLLMError(
                "EMPTY_DOCUMENT_SUMMARY",
                "The model returned an empty document summary.",
            )
        return normalized, 1

    async def _summarize_community_sources(
        self,
        sources: Sequence[SummarySource],
        *,
        instruction: str = "请生成该知识库的社区摘要。",
    ) -> tuple[str, int]:
        content, attempts = await self._complete(
            messages=build_community_messages(sources, instruction=instruction),
            max_tokens=self.settings.document_summary_final_max_tokens,
        )
        normalized = content.strip()
        if not normalized:
            raise DocumentSummaryLLMError(
                "EMPTY_COMMUNITY_SUMMARY",
                "The model returned an empty community summary.",
            )
        return normalized, 1

    async def _complete(
        self,
        *,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> tuple[str, int]:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.document_summary_max_attempts + 1):
            try:
                async with self.request_semaphore:
                    response = await self._client.post(
                        build_chat_completions_url(self.base_url),
                        headers=build_llm_headers(self.api_key),
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "temperature": self.settings.document_summary_temperature,
                            "max_tokens": max_tokens,
                            "extra_body": {"enable_thinking": False},
                        },
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.is_error:
                    raise DocumentSummaryLLMError(
                        "UPSTREAM_REQUEST_REJECTED",
                        f"LLM API returned HTTP {response.status_code}: {response.text[:500]}",
                        attempts=attempt,
                    )
                return parse_completion_content(response.json()), attempt
            except DocumentSummaryLLMError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt >= self.settings.document_summary_max_attempts:
                    break
                await asyncio.sleep(
                    self.settings.document_summary_retry_base_delay_seconds * (2 ** (attempt - 1))
                )
        raise DocumentSummaryLLMError(
            "UPSTREAM_SERVICE_ERROR",
            f"Document summary LLM request failed: {last_error}",
            attempts=self.settings.document_summary_max_attempts,
        ) from last_error


def get_document_summary_llm_config() -> tuple[str, str, str]:
    settings = get_settings()
    model_settings = get_model_settings().document_summary
    if not model_settings.model:
        model_settings = get_model_settings().llm
    return (
        model_settings.base_url.strip()
        or settings.llm_api_base_url.strip()
        or settings.llm_api_base.strip(),
        model_settings.api_key or settings.llm_api_key,
        model_settings.model.strip() or settings.llm_model.strip(),
    )


def build_chunk_messages(prompt_input: ChunkPromptInput) -> list[dict[str, str]]:
    meta_parts = []
    meta_parts.append(f"chunk_id: {prompt_input.chunk_id}")
    meta_parts.append(f"document_id: {prompt_input.document_id}")
    if prompt_input.section_path:
        meta_parts.append(f"section_path: {prompt_input.section_path}")
    if prompt_input.page_no is not None:
        meta_parts.append(f"page: {prompt_input.page_no}")
    meta_parts.append(f"content_type: {prompt_input.content_type}")

    meta_text = "\n".join(meta_parts)

    user_prompt = f"""请总结以下 Chunk 的核心内容。

【Chunk 元信息】
{meta_text}

【Chunk 正文】
{prompt_input.chunk_text}"""
    return [
        {"role": "system", "content": CHUNK_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_document_messages(
    sources: Sequence[SummarySource],
    *,
    instruction: str,
) -> list[dict[str, str]]:
    chunks_text = "\n\n---\n\n".join(
        f"Chunk [{i+1}] (section: {s.section_path}, source: {s.source_locator}):\n{s.short_summary}"
        for i, s in enumerate(sources)
    )
    user_prompt = f"以下是文档中各 Chunk 的短摘要。请依据它们生成整篇文档的最终摘要。\n\n{chunks_text}"
    return [
        {"role": "system", "content": DOCUMENT_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_community_messages(
    sources: Sequence[SummarySource],
    *,
    instruction: str,
) -> list[dict[str, str]]:
    chunks_text = "\n\n---\n\n".join(
        f"[{i+1}] {s.short_summary}" for i, s in enumerate(sources)
    )
    user_prompt = f"以下是同一社区/主题的多个文档摘要。请生成一条概括性摘要。\n\n{chunks_text}"
    return [
        {"role": "system", "content": COMMUNITY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def parse_completion_content(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise DocumentSummaryLLMError("INVALID_LLM_RESPONSE", "Response is not an object.")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise DocumentSummaryLLMError("INVALID_LLM_RESPONSE", "Response has no choices.")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise DocumentSummaryLLMError("INVALID_LLM_RESPONSE", "Response has no message content.")
    return content.strip()


def extract_json_from_reasoning(content: str) -> str:
    content = content.strip()
    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return content
    except json.JSONDecodeError:
        pass
    json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content, re.DOTALL)
    if json_match:
        candidate = json_match.group(0)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            pass
    raise ValueError(f"No valid JSON found in response: {content[:500]}")


def validate_chunk_extraction(
    raw_content: str, prompt_input: ChunkPromptInput
) -> ChunkKnowledgeExtractionPayload:
    # Model outputs plain text summary directly
    summary = raw_content.strip()
    if not summary:
        raise ValueError("Summary is empty")
    # Clean up any JSON artifacts if model accidentally outputs them
    if summary.startswith("{"):
        try:
            parsed = json.loads(summary)
            if isinstance(parsed, dict) and "short_summary" in parsed:
                summary = str(parsed["short_summary"]).strip()
        except json.JSONDecodeError:
            pass
    return ChunkKnowledgeExtractionPayload(short_summary=summary)
