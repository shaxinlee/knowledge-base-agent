from typing import Any, cast

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.base import Base
from app.dev.seed_demo_fixture import (
    DEMO_FILE_NAME,
    DEMO_KB_NAME,
    DEMO_USER_USERNAME,
    seed_demo_fixture,
)
from app.models import ChunkMetadata, File, KnowledgeBase, User
from app.services.embedding import LocalDemoEmbeddingClient, get_embedding_client
from app.services.reranker import LocalDemoRerankerClient, get_reranker_client
from app.services.vector_index import VectorSearchHit


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        self.objects[(bucket, key)] = {
            "data": data,
            "content_type": content_type,
            "metadata": metadata,
        }

    def get_object(self, *, bucket: str, key: str) -> bytes:
        return cast(bytes, self.objects[(bucket, key)]["data"])


class FakeVectorIndexClient:
    collection_name = "chunks"

    def __init__(self) -> None:
        self.vector_sizes: list[int] = []
        self.points: list[dict[str, Any]] = []
        self.deactivated_point_ids: list[str] = []

    def ensure_collection(self, *, vector_size: int) -> None:
        self.vector_sizes.append(vector_size)

    def upsert_points(self, *, points: list[dict[str, Any]]) -> None:
        self.points.extend(points)

    def deactivate_points(self, *, point_ids: list[str]) -> None:
        self.deactivated_point_ids.extend(point_ids)

    def search_points(
        self,
        *,
        vector: list[float],
        knowledge_base_id: str,
        limit: int,
    ) -> list[VectorSearchHit]:
        return []


def _make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_seed_demo_fixture_creates_indexed_file_chunks_storage_and_qdrant_points() -> None:
    session_factory = _make_session_factory()
    storage = FakeObjectStorage()
    vector_index_client = FakeVectorIndexClient()

    with session_factory() as db:
        result = seed_demo_fixture(
            db,
            vector_index_client=vector_index_client,
            storage=storage,
        )

        knowledge_base = db.scalar(select(KnowledgeBase).where(KnowledgeBase.name == DEMO_KB_NAME))
        file = db.scalar(select(File).where(File.file_name == DEMO_FILE_NAME))
        demo_user = db.scalar(select(User).where(User.username == DEMO_USER_USERNAME))
        assert file is not None
        chunks = db.scalars(
            select(ChunkMetadata)
            .where(ChunkMetadata.file_id == file.id)
            .order_by(ChunkMetadata.chunk_index)
        ).all()

    assert knowledge_base is not None
    assert demo_user is not None
    assert result.knowledge_base_id == str(knowledge_base.id)
    assert result.file_id == str(file.id)
    assert file.status == "indexed"
    assert len(chunks) == 3
    assert all(chunk.is_active for chunk in chunks)
    assert all(chunk.tsv for chunk in chunks)
    assert vector_index_client.vector_sizes == [2]
    assert len(vector_index_client.points) == 3
    assert {point["id"] for point in vector_index_client.points} == {
        str(chunk.id) for chunk in chunks
    }
    stored_object = storage.objects[(file.storage_bucket, file.storage_key)]
    stored_metadata = cast(dict[str, str], stored_object["metadata"])
    assert stored_metadata["file_id"] == str(file.id)
    assert stored_metadata["source"] == "demo_fixture"


def test_seed_demo_fixture_is_idempotent_and_deactivates_previous_chunks() -> None:
    session_factory = _make_session_factory()
    vector_index_client = FakeVectorIndexClient()

    with session_factory() as db:
        first = seed_demo_fixture(db, vector_index_client=vector_index_client)
        second = seed_demo_fixture(db, vector_index_client=vector_index_client)
        active_chunks = db.scalars(
            select(ChunkMetadata).where(ChunkMetadata.is_active.is_(True))
        ).all()

    assert first.knowledge_base_id == second.knowledge_base_id
    assert first.file_id == second.file_id
    assert sorted(vector_index_client.deactivated_point_ids) == sorted(first.chunk_ids)
    assert {str(chunk.id) for chunk in active_chunks} == set(second.chunk_ids)


def test_demo_fixture_clients_are_selected_when_enabled(monkeypatch: Any) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_fixture_enabled", True)

    embedding_client = get_embedding_client()
    reranker_client = get_reranker_client()

    assert isinstance(embedding_client, LocalDemoEmbeddingClient)
    assert isinstance(reranker_client, LocalDemoRerankerClient)
    assert embedding_client.embed_texts(["井下落鱼可视化工具"]) == embedding_client.embed_texts(
        ["井下落鱼可视化工具"]
    )
    scores = reranker_client.rerank(
        query="井下落鱼可视化工具 使用步骤",
        documents=[
            "井下落鱼可视化工具 使用步骤 第一第二第三",
            "封隔器通用技术条件",
        ],
    )
    assert scores[0] > scores[1]
