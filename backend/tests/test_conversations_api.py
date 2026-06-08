from collections.abc import Generator, Sequence
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.conversations import (
    get_bm25_index_client,
    get_embedding_client,
    get_llm_client,
    get_reranker_client,
    get_vector_index_client,
)
from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    ChunkMetadata,
    Conversation,
    ConversationStatus,
    Feedback,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    Message,
    MessageCitation,
    MessageTrace,
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
from app.services.llm import LLMAnswer, LLMClientProtocol
from app.services.reranker import RerankerClientProtocol
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


class FakeLLMClient:
    model = "fake-llm"
    prompt_version = "fake-prompt-v1"

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    def generate_answer(self, *, query: str, contexts: Sequence[Any]) -> LLMAnswer:
        self.requests.append({"query": query, "contexts": list(contexts)})
        return LLMAnswer(
            content=f"LLM answer for {query} [1]",
            model=self.model,
            prompt_version=self.prompt_version,
            raw_prompt_snapshot="fake prompt",
            token_usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

    def stream_answer(self, *, query: str, contexts: Sequence[Any]) -> Generator[str, None, None]:
        answer = self.generate_answer(query=query, contexts=contexts)
        yield answer.content


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
    vector_index_client: FakeVectorIndexClient,
    reranker_client: FakeRerankerClient | None = None,
    llm_client: FakeLLMClient | None = None,
    bm25_index_client: FakeBM25IndexClient | None = None,
) -> None:
    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    def override_embedding_client() -> EmbeddingClientProtocol:
        return embedding_client

    def override_vector_index_client() -> VectorIndexClientProtocol:
        return vector_index_client

    def override_reranker_client() -> RerankerClientProtocol:
        return reranker_client or FakeRerankerClient()

    def override_llm_client() -> LLMClientProtocol:
        return llm_client or FakeLLMClient()

    def override_bm25_index_client() -> BM25IndexClientProtocol:
        return bm25_index_client or FakeBM25IndexClient()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_embedding_client] = override_embedding_client
    app.dependency_overrides[get_bm25_index_client] = override_bm25_index_client
    app.dependency_overrides[get_llm_client] = override_llm_client
    app.dependency_overrides[get_reranker_client] = override_reranker_client
    app.dependency_overrides[get_vector_index_client] = override_vector_index_client


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_indexed_chunk(session_factory: sessionmaker[Session]) -> tuple[UUID, UUID]:
    with session_factory() as db:
        create_default_admin(db)
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        reader = User(
            email="reader@example.local",
            username="reader",
            password_hash=hash_password("ReaderPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        reader.profile = UserProfile(display_name="Reader")
        other = User(
            email="other@example.local",
            username="other",
            password_hash=hash_password("OtherPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        other.profile = UserProfile(display_name="Other")
        knowledge_base = KnowledgeBase(
            name="Chat KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        db.add_all([reader, other, knowledge_base])
        db.flush()

        file = File(
            knowledge_base_id=knowledge_base.id,
            file_name="chat.txt",
            file_ext=".txt",
            mime_type="text/plain",
            file_size=12,
            file_hash="f" * 64,
            storage_bucket="raw-files",
            storage_key="chat",
            status=FileStatus.INDEXED.value,
            created_by=admin.id,
        )
        db.add(file)
        db.flush()
        parse_job = ParseJob(
            file_id=file.id,
            knowledge_base_id=knowledge_base.id,
            status=ParseJobStatus.INDEXED.value,
            progress=100,
            created_by=admin.id,
        )
        db.add(parse_job)
        db.flush()
        chunk = ChunkMetadata(
            knowledge_base_id=knowledge_base.id,
            file_id=file.id,
            parse_job_id=parse_job.id,
            chunk_index=0,
            content="demo answer evidence",
            content_hash="f" * 64,
            token_count=3,
            source_type="txt",
            source_locator="txt:block-1",
            is_active=True,
            tsv="demo answer evidence",
        )
        db.add(chunk)
        db.commit()
        return knowledge_base.id, chunk.id


def _seed_empty_knowledge_base(session_factory: sessionmaker[Session]) -> UUID:
    with session_factory() as db:
        create_default_admin(db)
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        reader = User(
            email="reader@example.local",
            username="reader",
            password_hash=hash_password("ReaderPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        reader.profile = UserProfile(display_name="Reader")
        knowledge_base = KnowledgeBase(
            name="Empty KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        db.add_all([reader, knowledge_base])
        db.commit()
        return knowledge_base.id


def test_user_can_create_conversation_and_send_non_stream_message_with_citation() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_id = _seed_indexed_chunk(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_id),
                score=0.9,
                payload={"chunk_id": str(chunk_id), "knowledge_base_id": str(knowledge_base_id)},
            )
        ]
    )
    reranker_client = FakeRerankerClient(scores=[0.75])
    llm_client = FakeLLMClient()
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        llm_client,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Demo Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "demo answer", "stream": False},
        )
        assert message_response.status_code == 200
        body = message_response.json()
        assert body["user_message"]["content"] == "demo answer"
        assistant = body["assistant_message"]
        assert assistant["role"] == "assistant"
        assert assistant["content"] == "LLM answer for demo answer [1]"
        assert assistant["citations"][0]["chunk_id"] == str(chunk_id)
        assert assistant["citations"][0]["file_name"] == "chat.txt"
        assert assistant["citations"][0]["source_locator"] == "txt:block-1"

        detail_response = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=_headers(token),
        )
        assert detail_response.status_code == 200
        assert len(detail_response.json()["messages"]) == 2

        with session_factory() as db:
            conversations = db.scalars(select(Conversation)).all()
            messages = db.scalars(select(Message)).all()
            citation = db.scalar(select(MessageCitation))
            trace = db.scalar(select(MessageTrace))
        assert len(conversations) == 1
        assert len(messages) == 2
        assert citation is not None
        assert trace is not None
        assert trace.query_text == "demo answer"
        assert trace.retrieved_chunk_ids == [str(chunk_id)]
        assert trace.reranked_chunk_ids == [str(chunk_id)]
        assert trace.final_cited_chunk_ids == [str(chunk_id)]
        assert trace.reranker_scores == {str(chunk_id): 0.75}
        assert trace.embedding_model == "fake-bge-m3"
        assert trace.reranker_model == "fake-bge-reranker"
        assert trace.chat_model == "fake-llm"
        assert trace.prompt_version == "fake-prompt-v1"
        assert trace.raw_prompt_snapshot == "fake prompt"
        assert trace.token_usage == {"prompt_tokens": 10, "completion_tokens": 5}
        assert len(llm_client.requests) == 1
    finally:
        app.dependency_overrides.clear()


def test_user_can_send_stream_message_and_receive_sse_events() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_id = _seed_indexed_chunk(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_id),
                score=0.9,
                payload={"chunk_id": str(chunk_id), "knowledge_base_id": str(knowledge_base_id)},
            )
        ]
    )
    _install_overrides(session_factory, embedding_client, vector_index_client)
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Stream Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "demo answer", "stream": True},
        )
        assert message_response.status_code == 200
        assert message_response.headers["content-type"].startswith("text/event-stream")
        text = message_response.text
        assert "event: message_created" in text
        assert "event: retrieval" in text
        assert "event: token" in text
        assert "event: done" in text
        assert str(chunk_id) in text
        assert "LLM answer for demo answer [1]" in text

        with session_factory() as db:
            messages = db.scalars(select(Message)).all()
            citation = db.scalar(select(MessageCitation))
            trace = db.scalar(select(MessageTrace))
        assert len(messages) == 2
        assert citation is not None
        assert trace is not None
    finally:
        app.dependency_overrides.clear()


def test_user_can_submit_feedback_for_assistant_message_with_trace_telemetry() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_id = _seed_indexed_chunk(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_id),
                score=0.9,
                payload={"chunk_id": str(chunk_id), "knowledge_base_id": str(knowledge_base_id)},
            )
        ]
    )
    _install_overrides(session_factory, embedding_client, vector_index_client)
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Feedback Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "demo answer", "stream": False},
        )
        assert message_response.status_code == 200
        body = message_response.json()
        user_message_id = body["user_message"]["id"]
        assistant_message_id = body["assistant_message"]["id"]

        feedback_response = client.post(
            f"/api/v1/messages/{assistant_message_id}/feedback",
            headers=_headers(token),
            json={"rating": "helpful", "comment": "引用准确"},
        )
        assert feedback_response.status_code == 201
        feedback_body = feedback_response.json()
        assert feedback_body["rating"] == "helpful"
        assert feedback_body["comment"] == "引用准确"
        assert feedback_body["query_text"] == "demo answer"
        assert feedback_body["retrieved_chunk_ids"] == [str(chunk_id)]
        assert feedback_body["final_cited_chunk_ids"] == [str(chunk_id)]
        assert feedback_body["model_name"] == "fake-llm"
        assert feedback_body["prompt_version"] == "fake-prompt-v1"
        assert feedback_body["embedding_model"] == "fake-bge-m3"
        assert feedback_body["reranker_model"] == "fake-bge-reranker"

        updated_feedback_response = client.post(
            f"/api/v1/messages/{assistant_message_id}/feedback",
            headers=_headers(token),
            json={"rating": "unhelpful", "comment": "仍需改进"},
        )
        assert updated_feedback_response.status_code == 201
        assert updated_feedback_response.json()["rating"] == "unhelpful"

        detail_response = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=_headers(token),
        )
        assert detail_response.status_code == 200
        detail_messages = detail_response.json()["messages"]
        user_message = next(message for message in detail_messages if message["role"] == "user")
        assistant_message = next(
            message for message in detail_messages if message["role"] == "assistant"
        )
        assert user_message["feedback_rating"] is None
        assert assistant_message["feedback_rating"] == "unhelpful"

        user_message_feedback = client.post(
            f"/api/v1/messages/{user_message_id}/feedback",
            headers=_headers(token),
            json={"rating": "helpful"},
        )
        assert user_message_feedback.status_code == 422
        assert user_message_feedback.json()["error"]["code"] == "VALIDATION_ERROR"

        with session_factory() as db:
            feedback_rows = db.scalars(select(Feedback)).all()
        assert len(feedback_rows) == 1
        assert feedback_rows[0].rating == "unhelpful"
    finally:
        app.dependency_overrides.clear()


def test_user_cannot_read_another_users_conversation() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_id = _seed_indexed_chunk(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_id),
                score=0.9,
                payload={"chunk_id": str(chunk_id), "knowledge_base_id": str(knowledge_base_id)},
            )
        ]
    )
    _install_overrides(session_factory, embedding_client, vector_index_client)
    try:
        client = TestClient(app)
        reader_token = _login(client, "reader", "ReaderPassword123")
        other_token = _login(client, "other", "OtherPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(reader_token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Private Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        other_read = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=_headers(other_token),
        )
        assert other_read.status_code == 404
        assert other_read.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_user_can_soft_delete_own_conversation_and_other_user_cannot_delete() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_id = _seed_indexed_chunk(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_id),
                score=0.9,
                payload={"chunk_id": str(chunk_id), "knowledge_base_id": str(knowledge_base_id)},
            )
        ]
    )
    _install_overrides(session_factory, embedding_client, vector_index_client)
    try:
        client = TestClient(app)
        reader_token = _login(client, "reader", "ReaderPassword123")
        other_token = _login(client, "other", "OtherPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(reader_token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Disposable Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        other_delete = client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=_headers(other_token),
        )
        assert other_delete.status_code == 404
        assert other_delete.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

        own_delete = client.delete(
            f"/api/v1/conversations/{conversation_id}",
            headers=_headers(reader_token),
        )
        assert own_delete.status_code == 204
        assert own_delete.content == b""

        deleted_detail = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=_headers(reader_token),
        )
        assert deleted_detail.status_code == 404
        assert deleted_detail.json()["error"]["code"] == "RESOURCE_NOT_FOUND"

        list_response = client.get(
            f"/api/v1/conversations?knowledge_base_id={knowledge_base_id}",
            headers=_headers(reader_token),
        )
        assert list_response.status_code == 200
        assert list_response.json()["items"] == []

        with session_factory() as db:
            conversation = db.get(Conversation, UUID(conversation_id))
        assert conversation is not None
        assert conversation.status == ConversationStatus.DELETED.value
        assert conversation.deleted_at is not None
    finally:
        app.dependency_overrides.clear()


def test_empty_knowledge_base_message_returns_refusal_without_embedding_call() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_empty_knowledge_base(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(hits=[])
    llm_client = FakeLLMClient()
    _install_overrides(
        session_factory, embedding_client, vector_index_client, llm_client=llm_client
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Empty Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "anything", "stream": False},
        )

        assert message_response.status_code == 200
        assistant = message_response.json()["assistant_message"]
        assert "当前知识库中没有找到足够依据回答该问题" in assistant["content"]
        assert assistant["citations"] == []
        assert embedding_client.requests == []
        assert vector_index_client.searches == []
        assert llm_client.requests == []
    finally:
        app.dependency_overrides.clear()


def test_message_refuses_when_reranker_score_below_configured_threshold() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_id = _seed_indexed_chunk(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_id),
                score=0.9,
                payload={"chunk_id": str(chunk_id), "knowledge_base_id": str(knowledge_base_id)},
            )
        ]
    )
    reranker_client = FakeRerankerClient(scores=[0.2])
    llm_client = FakeLLMClient()
    settings = get_settings()
    original_threshold = settings.evidence_min_reranker_score
    settings.evidence_min_reranker_score = 0.8
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        llm_client,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")
        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Gated Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "demo answer", "stream": False},
        )

        assert message_response.status_code == 200
        assistant = message_response.json()["assistant_message"]
        assert "当前知识库中没有找到足够依据回答该问题" in assistant["content"]
        assert assistant["citations"] == []
        assert llm_client.requests == []
        with session_factory() as db:
            trace = db.scalar(select(MessageTrace))
        assert trace is not None
        assert trace.retrieved_chunk_ids == [str(chunk_id)]
        assert trace.final_cited_chunk_ids == []
    finally:
        settings.evidence_min_reranker_score = original_threshold
        app.dependency_overrides.clear()
