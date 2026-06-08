from collections.abc import Generator, Sequence
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.retrieval import (
    get_bm25_index_client,
    get_embedding_client,
    get_reranker_client,
    get_vector_index_client,
)
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    ChunkMetadata,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    ParseJob,
    ParseJobStatus,
    User,
    UserProfile,
    UserRole,
    UserStatus,
)
from app.services.auth import create_default_admin
from app.services.bm25_index import BM25IndexClientProtocol, BM25SearchHit
from app.services.embedding import EmbeddingClientProtocol
from app.services.reranker import RerankerClientProtocol
from app.services.retrieval import RetrievalCandidate, merge_candidates
from app.services.vector_index import VectorIndexClientProtocol, VectorSearchHit


class FakeEmbeddingClient:
    model = "fake-bge-m3"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.requests.append(list(texts))
        return [[1.0, float(len(text))] for text in texts]


class FakeVectorIndexClient:
    collection_name = "chunks"

    def __init__(self, hits: list[VectorSearchHit]) -> None:
        self.hits = hits
        self.searches: list[dict[str, Any]] = []

    def ensure_collection(self, *, vector_size: int) -> None:
        self.searches.append({"ensure_collection": vector_size})

    def upsert_points(self, *, points: list[dict[str, Any]]) -> None:
        self.searches.append({"upsert_points": points})

    def deactivate_points(self, *, point_ids: list[str]) -> None:
        self.searches.append({"deactivate_points": point_ids})

    def search_points(
        self,
        *,
        vector: list[float],
        knowledge_base_id: str,
        limit: int,
    ) -> list[VectorSearchHit]:
        self.searches.append(
            {"vector": vector, "knowledge_base_id": knowledge_base_id, "limit": limit}
        )
        return self.hits[:limit]


class FakeRerankerClient:
    model = "fake-bge-reranker"

    def __init__(self, scores: list[float] | None = None) -> None:
        self.scores = scores
        self.requests: list[dict[str, Any]] = []

    def rerank(self, *, query: str, documents: Sequence[str]) -> list[float]:
        self.requests.append({"query": query, "documents": list(documents)})
        if self.scores is not None:
            return self.scores[: len(documents)]
        return [float(len(documents) - index) for index, _document in enumerate(documents)]


class FakeBM25IndexClient:
    provider = "fake-bm25"
    index_name = "chunks_bm25"

    def __init__(self, *, enabled: bool = False, hits: list[BM25SearchHit] | None = None) -> None:
        self.enabled = enabled
        self.hits = hits or []
        self.searches: list[dict[str, Any]] = []

    def ensure_index(self) -> None:
        return

    def upsert_chunks(self, *, documents: list[Any]) -> None:
        return

    def deactivate_chunks(self, *, chunk_ids: list[str]) -> None:
        return

    def search(
        self,
        *,
        query: str,
        knowledge_base_id: str,
        limit: int,
    ) -> list[BM25SearchHit]:
        self.searches.append(
            {"query": query, "knowledge_base_id": knowledge_base_id, "limit": limit}
        )
        return self.hits[:limit]


def _make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override_db(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _install_overrides(
    session_factory: sessionmaker[Session],
    embedding_client: FakeEmbeddingClient,
    reranker_client: FakeRerankerClient,
    vector_index_client: FakeVectorIndexClient,
    bm25_index_client: FakeBM25IndexClient | None = None,
) -> None:
    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    def override_embedding_client() -> EmbeddingClientProtocol:
        return embedding_client

    def override_vector_index_client() -> VectorIndexClientProtocol:
        return vector_index_client

    def override_reranker_client() -> RerankerClientProtocol:
        return reranker_client

    def override_bm25_index_client() -> BM25IndexClientProtocol:
        return bm25_index_client or FakeBM25IndexClient()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_embedding_client] = override_embedding_client
    app.dependency_overrides[get_bm25_index_client] = override_bm25_index_client
    app.dependency_overrides[get_reranker_client] = override_reranker_client
    app.dependency_overrides[get_vector_index_client] = override_vector_index_client


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_indexed_chunks(session_factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID, UUID]:
    with session_factory() as db:
        create_default_admin(db)
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        user = User(
            email="reader@example.local",
            username="reader",
            password_hash=hash_password("ReaderPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        user.profile = UserProfile(display_name="Reader")
        kb_primary = KnowledgeBase(
            name="Primary KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        kb_other = KnowledgeBase(
            name="Other KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        db.add_all([user, kb_primary, kb_other])
        db.flush()

        primary_file = File(
            knowledge_base_id=kb_primary.id,
            file_name="primary.txt",
            file_ext=".txt",
            mime_type="text/plain",
            file_size=12,
            file_hash="a" * 64,
            storage_bucket="raw-files",
            storage_key="primary",
            status=FileStatus.INDEXED.value,
            created_by=admin.id,
        )
        other_file = File(
            knowledge_base_id=kb_other.id,
            file_name="other.txt",
            file_ext=".txt",
            mime_type="text/plain",
            file_size=12,
            file_hash="b" * 64,
            storage_bucket="raw-files",
            storage_key="other",
            status=FileStatus.INDEXED.value,
            created_by=admin.id,
        )
        db.add_all([primary_file, other_file])
        db.flush()

        primary_job = ParseJob(
            file_id=primary_file.id,
            knowledge_base_id=kb_primary.id,
            status=ParseJobStatus.INDEXED.value,
            progress=100,
            created_by=admin.id,
        )
        other_job = ParseJob(
            file_id=other_file.id,
            knowledge_base_id=kb_other.id,
            status=ParseJobStatus.INDEXED.value,
            progress=100,
            created_by=admin.id,
        )
        db.add_all([primary_job, other_job])
        db.flush()

        vector_chunk = ChunkMetadata(
            knowledge_base_id=kb_primary.id,
            file_id=primary_file.id,
            parse_job_id=primary_job.id,
            chunk_index=0,
            content="alpha vector evidence",
            content_hash="c" * 64,
            token_count=3,
            source_type="txt",
            source_locator="txt:block-1",
            is_active=True,
            tsv="alpha vector evidence",
        )
        full_text_chunk = ChunkMetadata(
            knowledge_base_id=kb_primary.id,
            file_id=primary_file.id,
            parse_job_id=primary_job.id,
            chunk_index=1,
            content="beta keyword evidence",
            content_hash="d" * 64,
            token_count=3,
            source_type="txt",
            source_locator="txt:block-2",
            is_active=True,
            tsv="beta keyword evidence",
        )
        other_chunk = ChunkMetadata(
            knowledge_base_id=kb_other.id,
            file_id=other_file.id,
            parse_job_id=other_job.id,
            chunk_index=0,
            content="alpha should not leak",
            content_hash="e" * 64,
            token_count=4,
            source_type="txt",
            source_locator="txt:block-1",
            is_active=True,
            tsv="alpha should not leak",
        )
        db.add_all([vector_chunk, full_text_chunk, other_chunk])
        db.commit()
        return kb_primary.id, kb_other.id, vector_chunk.id, other_chunk.id


def test_retrieval_search_merges_sources_and_filters_knowledge_base() -> None:
    session_factory = _make_session_factory()
    primary_kb_id, _other_kb_id, vector_chunk_id, other_chunk_id = _seed_indexed_chunks(
        session_factory
    )
    embedding_client = FakeEmbeddingClient()
    reranker_client = FakeRerankerClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(vector_chunk_id),
                score=0.8,
                payload={"chunk_id": str(vector_chunk_id), "knowledge_base_id": str(primary_kb_id)},
            ),
            VectorSearchHit(
                point_id=str(other_chunk_id),
                score=0.99,
                payload={"chunk_id": str(other_chunk_id), "knowledge_base_id": "other"},
            ),
        ]
    )
    _install_overrides(session_factory, embedding_client, reranker_client, vector_index_client)
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        response = client.post(
            f"/api/v1/knowledge-bases/{primary_kb_id}/retrieval/search",
            headers=_headers(token),
            json={"query": "alpha beta", "top_k": 8},
        )

        assert response.status_code == 200
        body = response.json()
        assert body["knowledge_base_id"] == str(primary_kb_id)
        assert body["query"] == "alpha beta"
        assert embedding_client.requests == [["alpha beta"]]
        assert vector_index_client.searches == [
            {"vector": [1.0, 10.0], "knowledge_base_id": str(primary_kb_id), "limit": 50}
        ]
        assert reranker_client.requests[0]["query"] == "alpha beta"

        returned_chunk_ids = {item["chunk_id"] for item in body["items"]}
        assert str(vector_chunk_id) in returned_chunk_ids
        assert str(other_chunk_id) not in returned_chunk_ids
        assert all(item["file_name"] == "primary.txt" for item in body["items"])
        assert all(item["source_locator"].startswith("txt:") for item in body["items"])
        assert {item["source"] for item in body["items"]} == {"hybrid", "full_text"}
    finally:
        app.dependency_overrides.clear()


def test_merge_candidates_uses_rrf_and_marks_hybrid_sources() -> None:
    vector_only_id = UUID("00000000-0000-0000-0000-000000000001")
    hybrid_id = UUID("00000000-0000-0000-0000-000000000002")
    full_text_only_id = UUID("00000000-0000-0000-0000-000000000003")

    merged = merge_candidates(
        [
            RetrievalCandidate(chunk_id=vector_only_id, score=0.99, source="vector"),
            RetrievalCandidate(chunk_id=hybrid_id, score=0.1, source="vector"),
        ],
        [
            RetrievalCandidate(chunk_id=hybrid_id, score=0.5, source="full_text"),
            RetrievalCandidate(chunk_id=full_text_only_id, score=0.4, source="full_text"),
        ],
    )

    assert [candidate.chunk_id for candidate in merged] == [
        hybrid_id,
        vector_only_id,
        full_text_only_id,
    ]
    assert merged[0].source == "hybrid"
    assert merged[0].score == (1 / 62) + (1 / 61)
    assert merged[1].score == 1 / 61


def test_retrieval_search_applies_reranker_ordering() -> None:
    session_factory = _make_session_factory()
    primary_kb_id, _other_kb_id, vector_chunk_id, other_chunk_id = _seed_indexed_chunks(
        session_factory
    )
    with session_factory() as db:
        full_text_chunk_id = db.scalar(
            select(ChunkMetadata.id).where(ChunkMetadata.content == "beta keyword evidence")
        )
    assert full_text_chunk_id is not None

    embedding_client = FakeEmbeddingClient()
    reranker_client = FakeRerankerClient(scores=[0.1, 0.9])
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(vector_chunk_id),
                score=0.8,
                payload={"chunk_id": str(vector_chunk_id), "knowledge_base_id": str(primary_kb_id)},
            ),
            VectorSearchHit(
                point_id=str(other_chunk_id),
                score=0.99,
                payload={"chunk_id": str(other_chunk_id), "knowledge_base_id": "other"},
            ),
        ]
    )
    _install_overrides(session_factory, embedding_client, reranker_client, vector_index_client)
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        response = client.post(
            f"/api/v1/knowledge-bases/{primary_kb_id}/retrieval/search",
            headers=_headers(token),
            json={"query": "alpha beta", "top_k": 2},
        )

        assert response.status_code == 200
        body = response.json()
        returned_chunk_ids = [item["chunk_id"] for item in body["items"]]
        assert returned_chunk_ids == [str(full_text_chunk_id), str(vector_chunk_id)]
        assert [item["score"] for item in body["items"]] == [0.9, 0.1]
        assert reranker_client.requests == [
            {
                "query": "alpha beta",
                "documents": ["alpha vector evidence", "beta keyword evidence"],
            }
        ]
    finally:
        app.dependency_overrides.clear()


def test_retrieval_uses_bm25_client_when_enabled() -> None:
    session_factory = _make_session_factory()
    primary_kb_id, _other_kb_id, vector_chunk_id, _other_chunk_id = _seed_indexed_chunks(
        session_factory
    )
    with session_factory() as db:
        bm25_chunk_id = db.scalar(
            select(ChunkMetadata.id).where(ChunkMetadata.content == "beta keyword evidence")
        )
    assert bm25_chunk_id is not None

    embedding_client = FakeEmbeddingClient()
    reranker_client = FakeRerankerClient(scores=[0.2, 0.8])
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(vector_chunk_id),
                score=0.8,
                payload={"chunk_id": str(vector_chunk_id), "knowledge_base_id": str(primary_kb_id)},
            )
        ]
    )
    bm25_index_client = FakeBM25IndexClient(
        enabled=True,
        hits=[BM25SearchHit(chunk_id=str(bm25_chunk_id), score=12.0)],
    )
    _install_overrides(
        session_factory,
        embedding_client,
        reranker_client,
        vector_index_client,
        bm25_index_client,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        response = client.post(
            f"/api/v1/knowledge-bases/{primary_kb_id}/retrieval/search",
            headers=_headers(token),
            json={"query": "VONETS 密码", "top_k": 2},
        )

        assert response.status_code == 200
        body = response.json()
        assert bm25_index_client.searches == [
            {"query": "VONETS 密码", "knowledge_base_id": str(primary_kb_id), "limit": 50}
        ]
        assert [item["chunk_id"] for item in body["items"]] == [
            str(bm25_chunk_id),
            str(vector_chunk_id),
        ]
        assert body["items"][0]["source"] == "full_text"
    finally:
        app.dependency_overrides.clear()


def test_retrieval_rejects_inactive_knowledge_base() -> None:
    session_factory = _make_session_factory()
    primary_kb_id, _other_kb_id, _vector_chunk_id, _other_chunk_id = _seed_indexed_chunks(
        session_factory
    )
    embedding_client = FakeEmbeddingClient()
    reranker_client = FakeRerankerClient()
    vector_index_client = FakeVectorIndexClient(hits=[])
    _install_overrides(session_factory, embedding_client, reranker_client, vector_index_client)
    try:
        with session_factory() as db:
            knowledge_base = db.get(KnowledgeBase, primary_kb_id)
            assert knowledge_base is not None
            knowledge_base.status = KnowledgeBaseStatus.DELETED.value
            db.commit()

        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")
        response = client.post(
            f"/api/v1/knowledge-bases/{primary_kb_id}/retrieval/search",
            headers=_headers(token),
            json={"query": "alpha"},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()
