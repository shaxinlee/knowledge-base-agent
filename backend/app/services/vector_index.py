from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.core.config import get_settings
from app.core.errors import ApiError


@dataclass(frozen=True)
class VectorSearchHit:
    point_id: str
    score: float
    payload: dict[str, Any]


class VectorIndexClientProtocol(Protocol):
    collection_name: str

    def ensure_collection(self, *, vector_size: int) -> None:
        pass

    def upsert_points(self, *, points: list[dict[str, Any]]) -> None:
        pass

    def deactivate_points(self, *, point_ids: list[str]) -> None:
        pass

    def search_points(
        self,
        *,
        vector: list[float],
        knowledge_base_id: str,
        limit: int,
    ) -> list[VectorSearchHit]:
        pass


class QdrantVectorIndexClient:
    def __init__(
        self,
        *,
        base_url: str,
        collection_name: str,
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection_name = collection_name
        self.timeout_seconds = timeout_seconds

    def ensure_collection(self, *, vector_size: int) -> None:
        collection_url = f"{self.base_url}/collections/{self.collection_name}"
        try:
            current = httpx.get(collection_url, timeout=self.timeout_seconds)
            if current.status_code == 200:
                return
            if current.status_code != 404:
                current.raise_for_status()

            response = httpx.put(
                collection_url,
                json={"vectors": {"size": vector_size, "distance": "Cosine"}},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Qdrant collection initialization failed.",
                status_code=502,
                details={
                    "service": "qdrant",
                    "collection": self.collection_name,
                    "error": str(exc),
                },
            ) from exc

    def upsert_points(self, *, points: list[dict[str, Any]]) -> None:
        if not points:
            return

        try:
            response = httpx.put(
                f"{self.base_url}/collections/{self.collection_name}/points",
                params={"wait": "true"},
                json={"points": points},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Qdrant point upsert failed.",
                status_code=502,
                details={
                    "service": "qdrant",
                    "collection": self.collection_name,
                    "error": str(exc),
                },
            ) from exc

    def deactivate_points(self, *, point_ids: list[str]) -> None:
        if not point_ids:
            return

        try:
            response = httpx.post(
                f"{self.base_url}/collections/{self.collection_name}/points/payload",
                params={"wait": "true"},
                json={"payload": {"is_active": False}, "points": point_ids},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Qdrant point deactivation failed.",
                status_code=502,
                details={
                    "service": "qdrant",
                    "collection": self.collection_name,
                    "point_count": len(point_ids),
                    "error": str(exc),
                },
            ) from exc

    def search_points(
        self,
        *,
        vector: list[float],
        knowledge_base_id: str,
        limit: int,
    ) -> list[VectorSearchHit]:
        try:
            response = httpx.post(
                f"{self.base_url}/collections/{self.collection_name}/points/search",
                json={
                    "vector": vector,
                    "limit": limit,
                    "with_payload": True,
                    "filter": {
                        "must": [
                            {
                                "key": "knowledge_base_id",
                                "match": {"value": knowledge_base_id},
                            },
                            {"key": "is_active", "match": {"value": True}},
                        ]
                    },
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Qdrant vector search failed.",
                status_code=502,
                details={
                    "service": "qdrant",
                    "collection": self.collection_name,
                    "error": str(exc),
                },
            ) from exc

        payload = response.json()
        raw_hits = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(raw_hits, list):
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Qdrant search returned an unsupported response shape.",
                status_code=502,
                details={"service": "qdrant", "collection": self.collection_name},
            )

        hits: list[VectorSearchHit] = []
        for raw_hit in raw_hits:
            if not isinstance(raw_hit, dict):
                continue
            raw_payload = raw_hit.get("payload")
            hits.append(
                VectorSearchHit(
                    point_id=str(raw_hit.get("id") or ""),
                    score=float(raw_hit.get("score") or 0.0),
                    payload=raw_payload if isinstance(raw_payload, dict) else {},
                )
            )
        return hits


def get_vector_index_client() -> QdrantVectorIndexClient:
    settings = get_settings()
    return QdrantVectorIndexClient(
        base_url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
    )
