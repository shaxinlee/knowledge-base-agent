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

CHUNK_PROMPT_VERSION = "chunk-knowledge-extraction-v1"
DOCUMENT_PROMPT_VERSION = "document-summary-v1"
COMMUNITY_PROMPT_VERSION = "knowledge-base-community-summary-v1"

CHUNK_SYSTEM_PROMPT = """你是一个通用文档知识抽取器。

你的任务是：仅依据输入的一个文本 Chunk，抽取可用于文档摘要、主题聚类、文档关系图谱和证据追溯的结构化信息。

输入可能来自制度、合同、会议纪要、产品文档、技术文档、论文、新闻、邮件、报告、操作手册或其他通用文本。

必须严格遵守以下规则：

1. 只能依据输入 Chunk 原文，不得使用外部知识，不得补充、猜测或改写事实。
2. 不要因为文本中出现多个术语，就推断它们之间存在关系。
3. 所有抽取结果必须尽量忠实保留原文语义，不夸大、不泛化。
4. 若原文信息不足，使用空数组 [] 或 null，不得编造。
5. short_summary 应概括 Chunk 的核心信息，使用 1~2 句，尽量不超过 120 个中文字符。
6. topics 是抽象主题，不应直接复制完整原句；通常输出 1~5 个。
7. keywords 是适用于检索、聚类和图谱连接的关键词或短语；通常输出 3~10 个。
8. entities 仅抽取原文明确出现的实体，或可以直接规范化的实体。
9. assertions 仅记录原文中明确表达的内容，包括：
   - 事实
   - 定义
   - 规则
   - 要求
   - 流程
   - 决策
   - 待办
   - 观点
   - 结果
   - 风险
   - 限制
10. assertion 中：
    - statement 必须是完整、可独立理解的陈述；
    - subject、predicate、object 无法可靠判断时使用 null；
    - conditions 仅填写原文明确给出的条件、前提、例外或触发条件；
    - time_scope 仅填写原文明示的时间、期限或适用期间；
    - evidence_text 必须是原文中的连续片段；
    - 不得把背景描述误写为结论；
    - 不得把建议、推测、计划误写为已发生事实。
11. semantic_role 只能选择最主要的一种：
    DESCRIPTION：背景、说明、概述
    DEFINITION：定义、解释术语
    RULE：制度、规范、约束、权限规则
    REQUIREMENT：必须、应当、禁止、需要满足的要求
    PROCEDURE：步骤、流程、操作方式
    DECISION：已做出的决定
    ACTION_ITEM：待办事项、责任分配、后续动作
    FACT：客观事实、事件、状态
    CLAIM：观点、判断、主张、推测
    RESULT：结果、数据结论、比较结论
    RISK：风险、潜在问题、影响
    LIMITATION：限制、例外、边界、未覆盖情况
    REFERENCE：引用、附件、目录、参考资料
    OTHER：无法归类
12. importance 取值范围为 0 到 1：
    - 0.85~1.00：核心规则、关键决定、关键结论、核心流程、重大风险、关键约束；
    - 0.60~0.84：明确且有价值的信息；
    - 0.30~0.59：一般说明、背景、辅助信息；
    - 0.00~0.29：目录、页眉页脚、重复内容、无意义 OCR、信息量很低内容。
13. quality_flags 可从以下值中选择：
    OCR_NOISE
    INCOMPLETE_SENTENCE
    DUPLICATE_CONTENT
    LOW_INFORMATION
    TABLE_CONTENT
    FIGURE_CAPTION
    HEADER_FOOTER
    REFERENCE_LIST
    NONE
14. 输出必须是合法 JSON。
15. 不输出 Markdown，不输出解释，不输出任何 JSON 以外的内容。"""

OUTPUT_SCHEMA_TEXT = """{
  "chunk_id": "string",
  "semantic_role": "DESCRIPTION | DEFINITION | RULE | REQUIREMENT | PROCEDURE | DECISION | ACTION_ITEM | FACT | CLAIM | RESULT | RISK | LIMITATION | REFERENCE | OTHER",
  "short_summary": "string",
  "topics": ["string"],
  "keywords": ["string"],
  "entities": [
    {
      "name": "string",
      "normalized_name": "string | null",
      "type": "PERSON | ORG | ROLE | PRODUCT | PROJECT | SYSTEM | DOCUMENT | LOCATION | DATE | TIME | MONEY | METRIC | METHOD | POLICY | EVENT | OTHER"
    }
  ],
  "assertions": [
    {
      "statement": "string",
      "statement_type": "FACT | RULE | REQUIREMENT | PROCEDURE | DECISION | ACTION_ITEM | CLAIM | RESULT | RISK | LIMITATION | DEFINITION",
      "subject": "string | null",
      "predicate": "string | null",
      "object": "string | null",
      "conditions": ["string"],
      "time_scope": "string | null",
      "polarity": "POSITIVE | NEGATIVE | NEUTRAL",
      "certainty": "HIGH | MEDIUM | LOW",
      "evidence_text": "string"
    }
  ],
  "importance": 0.0,
  "quality_flags": [
    "OCR_NOISE | INCOMPLETE_SENTENCE | DUPLICATE_CONTENT | LOW_INFORMATION | TABLE_CONTENT | FIGURE_CAPTION | HEADER_FOOTER | REFERENCE_LIST | NONE"
  ]
}"""

DOCUMENT_SYSTEM_PROMPT = """你是一个通用文档摘要器。只能依据输入的 Chunk 短摘要生成整篇文档摘要，不得使用外部知识。

要求：
1. 概括文档的核心主题、事实、定义、规则、要求、流程、决定、结果、风险和限制。
2. 不得把建议、推测、计划或待办改写为已发生事实。
3. 合并重复信息，但保留原文明示的条件、例外、时间范围和重要数值。
4. 按输入内容的原始顺序和逻辑组织。
5. 信息不足时如实说明，不得编造。
6. 只输出摘要正文，不输出 JSON、Markdown 标题、处理说明或 Chunk 清单。"""

COMMUNITY_SYSTEM_PROMPT = """你是一个知识库社区摘要器。只能依据输入的文档摘要，概括该知识库所覆盖的知识社区，不得使用外部知识。

要求：
1. 说明知识库主要包含哪些主题、业务领域、对象、方法、流程、规则、结果、风险与限制。
2. 识别多个文档共同覆盖的内容和彼此互补的内容，但不得推断输入未明确表达的关系。
3. 对存在明显差异、例外或边界的内容应分别说明，不得强行合并。
4. 不得把建议、计划、推测改写为已发生事实。
5. 文档较多时按主题组织成连贯的中文概述，避免逐文件机械罗列。
6. 只输出社区摘要正文，不输出 JSON、Markdown 标题、处理说明或文件清单。"""


@dataclass(frozen=True)
class ChunkPromptInput:
    chunk_id: str
    document_id: str
    section_path: str
    page_no: str | int | None
    content_type: str
    chunk_text: str


@dataclass(frozen=True)
class SummarySource:
    chunk_id: str
    section_path: str
    source_locator: str
    short_summary: str


class DocumentSummaryLLMError(RuntimeError):
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
            return validate_chunk_extraction(content, prompt_input), attempts
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            repair_messages = [
                *messages,
                {"role": "assistant", "content": content},
                {
                    "role": "user",
                    "content": (
                        "上一条输出未通过 JSON 或字段校验。请仅返回修复后的完整 JSON，"
                        "不要解释。若错误涉及 evidence_text，必须从 Chunk 原文逐字复制连续片段，"
                        "不得改写、补标点或合并不连续文本。若两段原文被页眉、页脚、页码或"
                        "其他文本隔开，必须拆成独立 assertion，或只保留其中一个连续证据片段"
                        "并同步收窄 statement。若仍无法保证 evidence_text 为原文连续片段，"
                        "必须删除对应 assertion；assertions 可以返回空数组。"
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
                return validate_chunk_extraction(repaired, prompt_input), attempts
            except (json.JSONDecodeError, ValidationError, ValueError) as repair_exc:
                raise DocumentSummaryLLMError(
                    "INVALID_EXTRACTION_RESPONSE",
                    str(repair_exc)[:2000],
                    attempts=attempts,
                ) from repair_exc

    async def summarize_document(
        self,
        sources: Sequence[SummarySource],
    ) -> tuple[str, int]:
        if not sources:
            raise DocumentSummaryLLMError(
                "NO_SUCCESSFUL_CHUNK_SUMMARIES",
                "No successful chunk summaries are available.",
            )
        current = list(sources)
        reduction_level = 0
        while estimate_sources_tokens(current) > self.settings.document_summary_max_input_tokens:
            batches = partition_sources(
                current,
                max_tokens=self.settings.document_summary_max_input_tokens,
            )
            reduced = await asyncio.gather(
                *[
                    self._summarize_sources(
                        batch,
                        instruction="请将这一连续片段压缩为忠实的中间摘要。",
                    )
                    for batch in batches
                ]
            )
            current = [
                SummarySource(
                    chunk_id=f"reduction-{reduction_level + 1}-{index + 1}",
                    section_path="",
                    source_locator="",
                    short_summary=summary,
                )
                for index, summary in enumerate(reduced)
            ]
            reduction_level += 1
        return await self._summarize_sources(current), reduction_level

    async def summarize_community(
        self,
        sources: Sequence[SummarySource],
    ) -> tuple[str, int]:
        if not sources:
            raise DocumentSummaryLLMError(
                "NO_DOCUMENT_SUMMARIES",
                "No document summaries are available for the knowledge base.",
            )
        current = list(sources)
        reduction_level = 0
        while estimate_sources_tokens(current) > self.settings.document_summary_max_input_tokens:
            batches = partition_sources(
                current,
                max_tokens=self.settings.document_summary_max_input_tokens,
            )
            reduced = await asyncio.gather(
                *[
                    self._summarize_community_sources(
                        batch,
                        instruction="请将这一组连续的文档摘要压缩为忠实的知识社区中间摘要。",
                    )
                    for batch in batches
                ]
            )
            current = [
                SummarySource(
                    chunk_id=f"community-reduction-{reduction_level + 1}-{index + 1}",
                    section_path="",
                    source_locator="",
                    short_summary=summary,
                )
                for index, summary in enumerate(reduced)
            ]
            reduction_level += 1
        return await self._summarize_community_sources(current), reduction_level

    async def _summarize_sources(
        self,
        sources: Sequence[SummarySource],
        *,
        instruction: str = "请生成整篇文档的最终摘要。",
    ) -> str:
        content, _attempts = await self._complete(
            messages=build_document_messages(sources, instruction=instruction),
            max_tokens=self.settings.document_summary_final_max_tokens,
        )
        normalized = content.strip()
        if not normalized:
            raise DocumentSummaryLLMError(
                "EMPTY_DOCUMENT_SUMMARY",
                "The model returned an empty document summary.",
            )
        return normalized

    async def _summarize_community_sources(
        self,
        sources: Sequence[SummarySource],
        *,
        instruction: str = "请生成该知识库的社区摘要。",
    ) -> str:
        content, _attempts = await self._complete(
            messages=build_community_messages(sources, instruction=instruction),
            max_tokens=self.settings.document_summary_final_max_tokens,
        )
        normalized = content.strip()
        if not normalized:
            raise DocumentSummaryLLMError(
                "EMPTY_COMMUNITY_SUMMARY",
                "The model returned an empty community summary.",
            )
        return normalized

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
    model_settings = get_model_settings().llm
    return (
        model_settings.base_url.strip()
        or settings.llm_api_base_url.strip()
        or settings.llm_api_base.strip(),
        model_settings.api_key or settings.llm_api_key,
        model_settings.model.strip() or settings.llm_model.strip(),
    )


def build_chunk_messages(prompt_input: ChunkPromptInput) -> list[dict[str, str]]:
    user_prompt = f"""请对以下 Chunk 执行通用知识抽取，并严格按照指定 JSON 结构返回。

【Chunk 元信息】
chunk_id: {prompt_input.chunk_id}
document_id: {prompt_input.document_id}
section_path: {prompt_input.section_path}
page_no: {json.dumps(prompt_input.page_no, ensure_ascii=False)}
content_type: {prompt_input.content_type}

【Chunk 原文】
{prompt_input.chunk_text}

【输出 JSON 结构】
{OUTPUT_SCHEMA_TEXT}"""
    return [
        {"role": "system", "content": CHUNK_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_document_messages(
    sources: Sequence[SummarySource],
    *,
    instruction: str,
) -> list[dict[str, str]]:
    source_text = "\n\n".join(
        (
            f"[{index}]\n"
            f"chunk_id: {source.chunk_id}\n"
            f"section_path: {source.section_path}\n"
            f"source_locator: {source.source_locator}\n"
            f"short_summary: {source.short_summary}"
        )
        for index, source in enumerate(sources, start=1)
    )
    return [
        {"role": "system", "content": DOCUMENT_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{instruction}\n\n【按原文顺序排列的 Chunk 短摘要】\n{source_text}",
        },
    ]


def build_community_messages(
    sources: Sequence[SummarySource],
    *,
    instruction: str,
) -> list[dict[str, str]]:
    source_text = "\n\n".join(
        (
            f"[{index}]\n"
            f"document_id: {source.chunk_id}\n"
            f"document_name: {source.section_path}\n"
            f"document_summary: {source.short_summary}"
        )
        for index, source in enumerate(sources, start=1)
    )
    return [
        {"role": "system", "content": COMMUNITY_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"{instruction}\n\n【文档摘要集合】\n{source_text}",
        },
    ]


def validate_chunk_extraction(
    content: str,
    prompt_input: ChunkPromptInput,
) -> ChunkKnowledgeExtractionPayload:
    payload = json.loads(content)
    extraction = ChunkKnowledgeExtractionPayload.model_validate(payload)
    if extraction.chunk_id != prompt_input.chunk_id:
        raise ValueError(
            f"chunk_id mismatch: expected {prompt_input.chunk_id}, got {extraction.chunk_id}"
        )
    for assertion in extraction.assertions:
        restored_evidence = restore_whitespace_normalized_evidence(
            assertion.evidence_text,
            prompt_input.chunk_text,
        )
        if restored_evidence is None:
            raise ValueError(
                f"evidence_text is not a continuous source substring: "
                f"{assertion.evidence_text[:120]}"
            )
        assertion.evidence_text = restored_evidence
    return extraction


def restore_whitespace_normalized_evidence(
    evidence_text: str,
    chunk_text: str,
) -> str | None:
    if evidence_text in chunk_text:
        return evidence_text

    compact_evidence = compact_evidence_text(evidence_text)
    if not compact_evidence:
        return None

    compact_source_characters: list[str] = []
    source_indexes: list[int] = []
    for index, character in enumerate(chunk_text):
        if character.isspace():
            continue
        if (
            character == "\\"
            and index + 1 < len(chunk_text)
            and chunk_text[index + 1] in r"\`*_{}[]()#+-.!%>"
        ):
            continue
        compact_source_characters.append(character)
        source_indexes.append(index)
    compact_source = "".join(compact_source_characters)
    compact_start = compact_source.find(compact_evidence)
    if compact_start < 0:
        return None

    compact_end = compact_start + len(compact_evidence) - 1
    source_start = source_indexes[compact_start]
    source_end = source_indexes[compact_end] + 1
    return chunk_text[source_start:source_end]


def compact_evidence_text(value: str) -> str:
    characters: list[str] = []
    for index, character in enumerate(value):
        if character.isspace():
            continue
        if (
            character == "\\"
            and index + 1 < len(value)
            and value[index + 1] in r"\`*_{}[]()#+-.!%>"
        ):
            continue
        characters.append(character)
    return "".join(characters)


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


def estimate_text_tokens(text: str) -> int:
    return max(len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]|[^\s]", text)), 1)


def estimate_sources_tokens(sources: Sequence[SummarySource]) -> int:
    return sum(
        estimate_text_tokens(source.short_summary)
        + estimate_text_tokens(source.section_path)
        + estimate_text_tokens(source.source_locator)
        + 20
        for source in sources
    )


def partition_sources(
    sources: Sequence[SummarySource],
    *,
    max_tokens: int,
) -> list[list[SummarySource]]:
    batches: list[list[SummarySource]] = []
    current: list[SummarySource] = []
    current_tokens = 0
    for source in sources:
        source_tokens = estimate_sources_tokens([source])
        if current and current_tokens + source_tokens > max_tokens:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(source)
        current_tokens += source_tokens
    if current:
        batches.append(current)
    return batches
