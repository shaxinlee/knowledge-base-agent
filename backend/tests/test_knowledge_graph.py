import asyncio
from collections.abc import Generator, Sequence
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    DocumentSummary,
    DocumentSummaryRelation,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseCommunitySummary,
    KnowledgeGraphState,
    ParseJob,
    ParseJobStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services.auth import create_default_admin
from app.services.document_summary_llm import SummarySource
from app.services.knowledge_graph import (
    GraphDocument,
    calculate_relation_drafts,
    cosine_similarity,
    get_knowledge_graph_response,
    rebuild_knowledge_graph,
)


class FakeEmbeddingClient:
    model = "fake-summary-embedding"

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = {
            "alpha": [1.0, 0.0],
            "alpha-related": [0.9, 0.1],
            "unrelated": [0.0, 1.0],
        }
        return [vectors[text] for text in texts]

    def embed_images(self, image_data_urls: Sequence[str]) -> list[list[float]]:
        return []


class FakeCommunityLLM:
    model = "fake-community-llm"

    async def summarize_community(
        self,
        sources: Sequence[SummarySource],
    ) -> tuple[str, int]:
        return "社区包含：" + "、".join(source.section_path for source in sources), 0


def make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def graph_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "knowledge_graph_similarity_threshold": 0.7,
        "knowledge_graph_max_relations_per_document": 2,
        "knowledge_graph_embedding_batch_size": 2,
        "knowledge_graph_community_concurrency": 1,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def seed_graph_documents(session_factory: sessionmaker[Session]) -> tuple[str, str]:
    with session_factory() as db:
        user = User(
            email="graph@example.local",
            username="graph-admin",
            password_hash="hash",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        db.flush()
        kb_a = KnowledgeBase(name="知识库 A", status="active", created_by=user.id)
        kb_b = KnowledgeBase(name="知识库 B", status="active", created_by=user.id)
        db.add_all([kb_a, kb_b])
        db.flush()
        for index, (kb, file_name, summary_text) in enumerate(
            [
                (kb_a, "alpha.pdf", "alpha"),
                (kb_a, "alpha-related.pdf", "alpha-related"),
                (kb_b, "unrelated.pdf", "unrelated"),
            ]
        ):
            file = File(
                knowledge_base_id=kb.id,
                file_name=file_name,
                file_ext=".pdf",
                file_size=100,
                file_hash=str(index) * 64,
                storage_bucket="raw-files",
                storage_key=file_name,
                status=FileStatus.INDEXED.value,
                created_by=user.id,
            )
            db.add(file)
            db.flush()
            job = ParseJob(
                file_id=file.id,
                knowledge_base_id=kb.id,
                status=ParseJobStatus.INDEXED.value,
                progress=100,
                created_by=user.id,
            )
            db.add(job)
            db.flush()
            file.latest_parse_job_id = job.id
            db.add(
                DocumentSummary(
                    knowledge_base_id=kb.id,
                    file_id=file.id,
                    parse_job_id=job.id,
                    status="completed",
                    summary=summary_text,
                    chunk_total=1,
                    chunk_completed=1,
                    chunk_succeeded=1,
                    chunk_failed=0,
                    chunk_prompt_version="chunk-v1",
                    document_prompt_version="document-v1",
                )
            )
        db.commit()
        return str(kb_a.id), str(kb_b.id)


def test_cosine_similarity_and_top_k_relations() -> None:
    documents = [
        GraphDocument(
            summary_id=uuid4(),
            file_id=uuid4(),
            parse_job_id=uuid4(),
            knowledge_base_id=uuid4(),
            file_name="a.pdf",
            file_ext=".pdf",
            knowledge_base_name="A",
            summary="a",
            summary_status="completed",
            summary_hash="a",
        ),
        GraphDocument(
            summary_id=uuid4(),
            file_id=uuid4(),
            parse_job_id=uuid4(),
            knowledge_base_id=uuid4(),
            file_name="b.pdf",
            file_ext=".pdf",
            knowledge_base_name="B",
            summary="b",
            summary_status="completed",
            summary_hash="b",
        ),
        GraphDocument(
            summary_id=uuid4(),
            file_id=uuid4(),
            parse_job_id=uuid4(),
            knowledge_base_id=uuid4(),
            file_name="c.pdf",
            file_ext=".pdf",
            knowledge_base_name="C",
            summary="c",
            summary_status="completed",
            summary_hash="c",
        ),
    ]
    vectors = {
        documents[0].summary_id: [1.0, 0.0],
        documents[1].summary_id: [0.9, 0.1],
        documents[2].summary_id: [0.0, 1.0],
    }

    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    drafts = calculate_relation_drafts(
        documents,
        vectors,
        threshold=0.7,
        max_relations_per_document=1,
    )
    assert len(drafts) == 1
    assert drafts[0].similarity > 0.99


def test_rebuild_graph_persists_relations_communities_and_cross_kb_filtering() -> None:
    session_factory = make_session_factory()
    kb_a_id, kb_b_id = seed_graph_documents(session_factory)
    settings = graph_settings()

    rebuilt = asyncio.run(
        rebuild_knowledge_graph(
            session_factory=session_factory,
            settings=settings,
            embedding_client=FakeEmbeddingClient(),
            llm_client=FakeCommunityLLM(),  # type: ignore[arg-type]
        )
    )
    assert rebuilt

    with session_factory() as db:
        state = db.scalar(select(KnowledgeGraphState))
        relations = list(db.scalars(select(DocumentSummaryRelation)).all())
        communities = list(db.scalars(select(KnowledgeBaseCommunitySummary)).all())
        assert state is not None
        assert state.status == "completed"
        assert state.document_count == 3
        assert len(relations) == 1
        assert not relations[0].cross_knowledge_base
        assert len(communities) == 2
        assert all(community.status == "completed" for community in communities)

        response = get_knowledge_graph_response(
            db,
            knowledge_base_id=None,
            include_cross_knowledge_base=True,
            min_similarity=0.7,
            settings=settings,
        )
        assert response.document_count == 3
        assert response.total_document_count == 3
        assert response.summarized_document_count == 3
        assert response.pending_summary_count == 0
        assert response.failed_summary_count == 0
        assert response.not_ready_document_count == 0
        assert response.relation_count == 1
        assert len(response.communities) == 2

        kb_a_response = get_knowledge_graph_response(
            db,
            knowledge_base_id=UUID(kb_a_id),
            include_cross_knowledge_base=False,
            min_similarity=0.7,
            settings=settings,
        )
        assert len(kb_a_response.nodes) == 2
        assert kb_a_response.total_document_count == 2
        assert kb_a_response.summarized_document_count == 2
        assert kb_a_response.relation_count == 1

        kb_b_response = get_knowledge_graph_response(
            db,
            knowledge_base_id=UUID(kb_b_id),
            include_cross_knowledge_base=False,
            min_similarity=0.7,
            settings=settings,
        )
        assert len(kb_b_response.nodes) == 1
        assert kb_b_response.relation_count == 0

        communities[0].status = "failed"
        db.commit()

    retried = asyncio.run(
        rebuild_knowledge_graph(
            session_factory=session_factory,
            settings=settings,
            embedding_client=FakeEmbeddingClient(),
            llm_client=FakeCommunityLLM(),  # type: ignore[arg-type]
        )
    )
    assert retried
    with session_factory() as db:
        assert all(
            community.status == "completed"
            for community in db.scalars(select(KnowledgeBaseCommunitySummary)).all()
        )


def test_graph_api_is_readable_by_users_but_refresh_is_admin_only() -> None:
    session_factory = make_session_factory()
    with session_factory() as db:
        create_default_admin(db)
        user = User(
            email="reader@example.local",
            username="reader",
            password_hash=hash_password("ReaderPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        db.commit()

    def override_db() -> Generator[Session, None, None]:
        with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        admin_login = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "AdminPassword123"},
        )
        user_login = client.post(
            "/api/v1/auth/login",
            json={"username": "reader", "password": "ReaderPassword123"},
        )
        assert admin_login.status_code == 200
        assert user_login.status_code == 200
        admin_headers = {
            "Authorization": f"Bearer {admin_login.json()['access_token']}"
        }
        user_headers = {
            "Authorization": f"Bearer {user_login.json()['access_token']}"
        }

        read_response = client.get("/api/v1/knowledge-graph", headers=user_headers)
        assert read_response.status_code == 200
        assert read_response.json()["nodes"] == []

        forbidden = client.post(
            "/api/v1/knowledge-graph/refresh",
            headers=user_headers,
            json={"force_embeddings": False},
        )
        assert forbidden.status_code == 403

        refresh_response = client.post(
            "/api/v1/knowledge-graph/refresh",
            headers=admin_headers,
            json={"force_embeddings": False},
        )
        assert refresh_response.status_code == 202
        assert refresh_response.json()["status"] == "pending"
    finally:
        app.dependency_overrides.clear()
