from datetime import datetime
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.errors import ApiError


class BM25ChunkDocument(BaseModel):
    chunk_id: str
    knowledge_base_id: str
    file_id: str
    parse_job_id: str
    file_name: str
    content: str
    source_locator: str
    source_type: str
    heading_path: list[str] | None = None
    is_active: bool = True
    created_at: datetime | None = None


class BM25SearchHit(BaseModel):
    chunk_id: str
    score: float
    raw: dict[str, Any] = Field(default_factory=dict)


class BM25IndexClientProtocol(Protocol):
    enabled: bool
    provider: str
    index_name: str

    def ensure_index(self) -> None:
        pass

    def upsert_chunks(self, *, documents: list[BM25ChunkDocument]) -> None:
        pass

    def deactivate_chunks(self, *, chunk_ids: list[str]) -> None:
        pass

    def delete_chunks(self, *, chunk_ids: list[str]) -> None:
        pass

    def search(
        self,
        *,
        query: str,
        knowledge_base_id: str,
        limit: int,
    ) -> list[BM25SearchHit]:
        pass


class DisabledBM25IndexClient:
    enabled = False
    provider = "disabled"
    index_name = ""

    def ensure_index(self) -> None:
        return

    def upsert_chunks(self, *, documents: list[BM25ChunkDocument]) -> None:
        return

    def deactivate_chunks(self, *, chunk_ids: list[str]) -> None:
        return

    def delete_chunks(self, *, chunk_ids: list[str]) -> None:
        return

    def search(
        self,
        *,
        query: str,
        knowledge_base_id: str,
        limit: int,
    ) -> list[BM25SearchHit]:
        return []


class OpenSearchBM25IndexClient:
    enabled = True
    provider = "opensearch"

    def __init__(
        self,
        *,
        base_url: str,
        index_name: str,
        index_analyzer: str,
        search_analyzer: str,
        timeout_seconds: int = 60,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.index_name = index_name
        self.index_analyzer = index_analyzer
        self.search_analyzer = search_analyzer
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def ensure_index(self) -> None:
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                current = client.get(self._index_url())
                if current.status_code == 200:
                    return
                if current.status_code != 404:
                    current.raise_for_status()
                response = client.put(self._index_url(), json=self.build_index_body())
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._error("BM25 index initialization failed.", exc) from exc

    def upsert_chunks(self, *, documents: list[BM25ChunkDocument]) -> None:
        if not documents:
            return
        body_lines: list[str] = []
        for document in documents:
            body_lines.append(
                to_json_line({"index": {"_index": self.index_name, "_id": document.chunk_id}})
            )
            body_lines.append(to_json_line(document.model_dump(mode="json")))
        body = "\n".join(body_lines) + "\n"
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/_bulk",
                    headers={"Content-Type": "application/x-ndjson"},
                    content=body,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._error("BM25 index request failed.", exc) from exc

        payload = response.json()
        if isinstance(payload, dict) and payload.get("errors") is True:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="BM25 index request failed.",
                status_code=502,
                details={
                    "service": "opensearch-bm25",
                    "index": self.index_name,
                    "errors": payload.get("items", [])[:3],
                },
            )

    def deactivate_chunks(self, *, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        # Check if index exists; if not, nothing to deactivate
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                check = client.get(self._index_url())
                if check.status_code == 404:
                    return
        except httpx.HTTPError:
            pass  # If we can't check, proceed to the deactivation attempt
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self._index_url()}/_update_by_query",
                    json={
                        "script": {
                            "source": "ctx._source.is_active = false",
                            "lang": "painless",
                        },
                        "query": {"terms": {"chunk_id": chunk_ids}},
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._error("BM25 deactivation request failed.", exc) from exc

    def delete_chunks(self, *, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return
        # Check if index exists; if not, nothing to delete
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                check = client.get(self._index_url())
                if check.status_code == 404:
                    return
        except httpx.HTTPError:
            pass  # If we can't check, proceed to the deletion attempt
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self._index_url()}/_delete_by_query",
                    json={"query": {"terms": {"chunk_id": chunk_ids}}},
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._error("BM25 chunk deletion failed.", exc) from exc

    def search(
        self,
        *,
        query: str,
        knowledge_base_id: str,
        limit: int,
    ) -> list[BM25SearchHit]:
        if not query.strip():
            return []
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self._index_url()}/_search",
                    json={
                        "size": limit,
                        "_source": ["chunk_id"],
                        "query": {
                            "bool": {
                                "filter": [
                                    {"term": {"knowledge_base_id": knowledge_base_id}},
                                    {"term": {"is_active": True}},
                                ],
                                "must": [
                                    {
                                        "multi_match": {
                                            "query": query,
                                            "fields": [
                                                "content^3",
                                                "heading_path^2",
                                                "file_name",
                                            ],
                                        }
                                    }
                                ],
                            }
                        },
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise self._error("BM25 search request failed.", exc) from exc

        payload = response.json()
        raw_hits = (
            (payload.get("hits") or {}).get("hits") if isinstance(payload, dict) else None
        ) or []
        hits: list[BM25SearchHit] = []
        for raw_hit in raw_hits:
            if not isinstance(raw_hit, dict):
                continue
            source = raw_hit.get("_source")
            if not isinstance(source, dict):
                continue
            chunk_id = source.get("chunk_id")
            if not chunk_id:
                continue
            hits.append(
                BM25SearchHit(
                    chunk_id=str(chunk_id),
                    score=float(raw_hit.get("_score") or 0.0),
                    raw=raw_hit,
                )
            )
        return hits

    def build_index_body(self) -> dict[str, Any]:
        return {
            "settings": {
                "analysis": {
                    "analyzer": {
                        "kb_ik_index": {"type": "custom", "tokenizer": self.index_analyzer},
                        "kb_ik_search": {"type": "custom", "tokenizer": self.search_analyzer},
                    }
                }
            },
            "mappings": {
                "properties": {
                    "chunk_id": {"type": "keyword"},
                    "knowledge_base_id": {"type": "keyword"},
                    "file_id": {"type": "keyword"},
                    "parse_job_id": {"type": "keyword"},
                    "file_name": {
                        "type": "text",
                        "analyzer": "kb_ik_index",
                        "search_analyzer": "kb_ik_search",
                        "fields": {"keyword": {"type": "keyword"}},
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "kb_ik_index",
                        "search_analyzer": "kb_ik_search",
                    },
                    "source_locator": {"type": "keyword"},
                    "source_type": {"type": "keyword"},
                    "heading_path": {
                        "type": "text",
                        "analyzer": "kb_ik_index",
                        "search_analyzer": "kb_ik_search",
                    },
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "date"},
                }
            },
        }

    def _index_url(self) -> str:
        return f"{self.base_url}/{self.index_name}"

    def _error(self, message: str, exc: httpx.HTTPError) -> ApiError:
        response = getattr(exc, "response", None)
        return ApiError(
            code="UPSTREAM_SERVICE_ERROR",
            message=message,
            status_code=502,
            details={
                "service": "opensearch-bm25",
                "index": self.index_name,
                "error": str(exc),
                "response": response.text[:500] if response is not None else None,
            },
        )


def to_json_line(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def get_bm25_index_client() -> BM25IndexClientProtocol:
    settings = get_settings()
    if not settings.bm25_enabled:
        return DisabledBM25IndexClient()
    return OpenSearchBM25IndexClient(
        base_url=settings.bm25_base_url,
        index_name=settings.bm25_index_name,
        index_analyzer=settings.bm25_index_analyzer,
        search_analyzer=settings.bm25_search_analyzer,
    )
