import asyncio
import json
import re
from typing import cast
from uuid import UUID

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.models import ChunkKnowledgeExtraction, DocumentSummary
from app.services.document_summary_llm import (
    CHUNK_PROMPT_VERSION,
    ChunkPromptInput,
    DocumentSummaryLLMClient,
    SummarySource,
    partition_sources,
    validate_chunk_extraction,
)
from app.services.document_summaries import release_worker_tasks


def valid_extraction(chunk_id: str, *, evidence: str = "原文证据") -> dict[str, object]:
    return {
        "chunk_id": chunk_id,
        "semantic_role": "FACT",
        "short_summary": "Chunk 说明了原文证据。",
        "topics": ["测试主题"],
        "keywords": ["原文", "证据", "测试"],
        "entities": [],
        "assertions": [
            {
                "statement": "Chunk 包含原文证据。",
                "statement_type": "FACT",
                "subject": "Chunk",
                "predicate": "包含",
                "object": "原文证据",
                "conditions": [],
                "time_scope": None,
                "polarity": "POSITIVE",
                "certainty": "HIGH",
                "evidence_text": evidence,
            }
        ],
        "importance": 0.7,
        "quality_flags": ["NONE"],
    }


def summary_settings(**overrides: object) -> Settings:
    payload: dict[str, object] = {
        "document_summary_global_request_concurrency": 16,
        "document_summary_http_max_connections": 20,
        "document_summary_http_max_keepalive_connections": 16,
        "document_summary_max_attempts": 1,
        "document_summary_retry_base_delay_seconds": 0,
        "document_summary_max_input_tokens": 24000,
    }
    payload.update(overrides)
    return Settings(_env_file=None, **payload)


def test_chunk_extraction_validation_requires_matching_id_and_continuous_evidence() -> None:
    prompt_input = ChunkPromptInput(
        chunk_id="chunk-1",
        document_id="file-1",
        section_path="第一章",
        page_no=1,
        content_type="text",
        chunk_text="这里包含原文证据，并且只能依据当前文本。",
    )

    extraction = validate_chunk_extraction(
        json.dumps(valid_extraction("chunk-1"), ensure_ascii=False),
        prompt_input,
    )
    assert extraction.chunk_id == "chunk-1"
    assert extraction.assertions[0].evidence_text == "原文证据"

    whitespace_payload = valid_extraction(
        "chunk-1",
        evidence="这里包含 原文证据，\n并且只能依据当前文本。",
    )
    whitespace_extraction = validate_chunk_extraction(
        json.dumps(whitespace_payload, ensure_ascii=False),
        prompt_input,
    )
    assert (
        whitespace_extraction.assertions[0].evidence_text
        == "这里包含原文证据，并且只能依据当前文本。"
    )

    escaped_prompt_input = ChunkPromptInput(
        chunk_id="chunk-1",
        document_id="file-1",
        section_path="第一章",
        page_no=1,
        content_type="text",
        chunk_text=(
            "违约金不超过合同总额的 5 \\%"
            "，提交\\_南京仲裁委员会\\_仲裁。"
        ),
    )
    escaped_payload = valid_extraction(
        "chunk-1",
        evidence="违约金不超过合同总额的 5 %，提交_南京仲裁委员会_仲裁。",
    )
    escaped_extraction = validate_chunk_extraction(
        json.dumps(escaped_payload, ensure_ascii=False),
        escaped_prompt_input,
    )
    assert (
        escaped_extraction.assertions[0].evidence_text
        == (
            "违约金不超过合同总额的 5 \\%"
            "，提交\\_南京仲裁委员会\\_仲裁。"
        )
    )

    with pytest.raises(ValueError, match="chunk_id mismatch"):
        validate_chunk_extraction(
            json.dumps(valid_extraction("chunk-2"), ensure_ascii=False),
            prompt_input,
        )
    with pytest.raises(ValueError, match="continuous source substring"):
        validate_chunk_extraction(
            json.dumps(
                valid_extraction("chunk-1", evidence="原文中不存在的证据"),
                ensure_ascii=False,
            ),
            prompt_input,
        )


def test_chunk_extraction_validation_rejects_none_combined_with_other_flags() -> None:
    prompt_input = ChunkPromptInput(
        chunk_id="chunk-1",
        document_id="file-1",
        section_path="",
        page_no=None,
        content_type="text",
        chunk_text="原文证据",
    )
    payload = valid_extraction("chunk-1")
    payload["quality_flags"] = ["NONE", "LOW_INFORMATION"]

    with pytest.raises(ValidationError, match="NONE cannot be combined"):
        validate_chunk_extraction(json.dumps(payload, ensure_ascii=False), prompt_input)


def test_settings_reject_http_pool_smaller_than_global_summary_concurrency() -> None:
    with pytest.raises(ValidationError, match="max_connections"):
        summary_settings(
            document_summary_global_request_concurrency=16,
            document_summary_http_max_connections=8,
        )


def test_chunk_requests_run_concurrently_but_respect_document_limit() -> None:
    async def run() -> tuple[int, list[str]]:
        in_flight = 0
        max_in_flight = 0
        completed: list[str] = []
        lock = asyncio.Lock()

        async def handler(request: httpx.Request) -> httpx.Response:
            nonlocal in_flight, max_in_flight
            payload = json.loads(request.content.decode("utf-8"))
            user_content = payload["messages"][1]["content"]
            chunk_id = cast(re.Match[str], re.search(r"chunk_id: (chunk-\d+)", user_content)).group(1)
            async with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            await asyncio.sleep(0.02)
            async with lock:
                in_flight -= 1
                completed.append(chunk_id)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    valid_extraction(chunk_id),
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
            )

        settings = summary_settings()
        client = DocumentSummaryLLMClient(
            base_url="http://vllm.test/v1",
            api_key="test",
            model="test-model",
            settings=settings,
            request_semaphore=asyncio.Semaphore(16),
            transport=httpx.MockTransport(handler),
        )
        document_semaphore = asyncio.Semaphore(8)

        async def extract(index: int) -> None:
            async with document_semaphore:
                await client.extract_chunk(
                    ChunkPromptInput(
                        chunk_id=f"chunk-{index}",
                        document_id="file-1",
                        section_path="",
                        page_no=index,
                        content_type="text",
                        chunk_text="原文证据",
                    )
                )

        await asyncio.gather(*(extract(index) for index in range(24)))
        await client.aclose()
        return max_in_flight, completed

    max_in_flight, completed = asyncio.run(run())
    assert 1 < max_in_flight <= 8
    assert len(completed) == 24


def test_document_summary_preserves_source_order_after_concurrent_reduction() -> None:
    async def run() -> list[list[str]]:
        observed_batches: list[list[str]] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode("utf-8"))
            user_content = payload["messages"][1]["content"]
            ids = re.findall(r"chunk_id: (chunk-\d+|reduction-\d+-\d+)", user_content)
            observed_batches.append(ids)
            await asyncio.sleep(0.01 if ids and ids[0].endswith("1") else 0.001)
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "；".join(ids)}}]},
            )

        settings = summary_settings(document_summary_max_input_tokens=80)
        client = DocumentSummaryLLMClient(
            base_url="http://vllm.test/v1",
            api_key="",
            model="test-model",
            settings=settings,
            request_semaphore=asyncio.Semaphore(16),
            transport=httpx.MockTransport(handler),
        )
        sources = [
            SummarySource(
                chunk_id=f"chunk-{index}",
                section_path=f"章节 {index}",
                source_locator=f"pdf:p{index}",
                short_summary=f"第 {index} 段摘要，包含足够长度以触发分层归并。",
            )
            for index in range(1, 7)
        ]
        summary, reduction_level = await client.summarize_document(sources)
        await client.aclose()
        assert reduction_level >= 1
        assert summary
        return observed_batches

    observed_batches = asyncio.run(run())
    first_level = [batch for batch in observed_batches if batch and batch[0].startswith("chunk-")]
    flattened = [chunk_id for batch in first_level for chunk_id in batch]
    assert flattened == [f"chunk-{index}" for index in range(1, 7)]


def test_partition_sources_never_drops_document_tail() -> None:
    sources = [
        SummarySource(
            chunk_id=f"chunk-{index}",
            section_path="",
            source_locator="",
            short_summary="摘要内容",
        )
        for index in range(20)
    ]
    batches = partition_sources(sources, max_tokens=60)
    assert [source.chunk_id for batch in batches for source in batch] == [
        source.chunk_id for source in sources
    ]
    assert CHUNK_PROMPT_VERSION == "chunk-knowledge-extraction-v1"


def test_graceful_worker_shutdown_releases_document_and_chunk_leases() -> None:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, class_=Session)
    ids = {
        "summary": UUID("00000000-0000-0000-0000-000000000001"),
        "kb": UUID("00000000-0000-0000-0000-000000000002"),
        "file": UUID("00000000-0000-0000-0000-000000000003"),
        "job": UUID("00000000-0000-0000-0000-000000000004"),
        "chunk": UUID("00000000-0000-0000-0000-000000000005"),
        "extraction": UUID("00000000-0000-0000-0000-000000000006"),
    }
    with session_factory() as db:
        db.add(
            DocumentSummary(
                id=ids["summary"],
                knowledge_base_id=ids["kb"],
                file_id=ids["file"],
                parse_job_id=ids["job"],
                status="running",
                priority=20,
                chunk_prompt_version=CHUNK_PROMPT_VERSION,
                document_prompt_version="document-summary-v1",
                worker_id="worker-1",
            )
        )
        db.add(
            ChunkKnowledgeExtraction(
                id=ids["extraction"],
                chunk_id=ids["chunk"],
                file_id=ids["file"],
                parse_job_id=ids["job"],
                status="running",
                prompt_version=CHUNK_PROMPT_VERSION,
            )
        )
        db.commit()

    release_worker_tasks(session_factory, worker_id="worker-1")

    with session_factory() as db:
        summary = db.scalar(select(DocumentSummary))
        extraction = db.scalar(select(ChunkKnowledgeExtraction))
        assert summary is not None
        assert extraction is not None
        assert summary.status == "pending"
        assert summary.worker_id is None
        assert summary.lease_expires_at is None
        assert extraction.status == "pending"
