import json
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
    get_image_description_client,
    get_knowledge_search_router,
    get_llm_client,
    get_object_storage,
    get_query_router,
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
    DocumentSummary,
    Feedback,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseCommunitySummary,
    KnowledgeBaseStatus,
    Message,
    MessageAttachment,
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
from app.services.image_descriptions import ImageDescriptionClientProtocol, ImageDescriptionInput
from app.services.llm import LLMAnswer, LLMClientProtocol
from app.rag.query_router import (
    KnowledgeSearchDecision,
    KnowledgeSearchRouterProtocol,
    QueryRouterProtocol,
    RouteDecision,
    RuleBasedQueryRouter,
)
from app.services.reranker import RerankerClientProtocol
from app.services.vector_index import VectorIndexClientProtocol, VectorSearchHit


class FakeEmbeddingClient:
    model = "fake-bge-m3"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.requests.append(list(texts))
        return [[1.0, float(len(text))] for text in texts]

    def embed_images(self, image_data_urls: Sequence[str]) -> list[list[float]]:
        self.requests.append([f"image:{len(image_data_url)}" for image_data_url in image_data_urls])
        return [[9.0, float(len(image_data_url))] for image_data_url in image_data_urls]


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
        modality: str | None = None,
    ) -> list[VectorSearchHit]:
        self.searches.append(
            {
                "vector": vector,
                "knowledge_base_id": knowledge_base_id,
                "limit": limit,
                "modality": modality,
            }
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

    def generate_answer(
        self,
        *,
        query: str,
        contexts: Sequence[Any],
        enable_thinking: bool = False,
    ) -> LLMAnswer:
        self.requests.append(
            {
                "query": query,
                "contexts": list(contexts),
                "enable_thinking": enable_thinking,
            }
        )
        return LLMAnswer(
            content=f"LLM answer for {query} [1]",
            model=self.model,
            prompt_version=self.prompt_version,
            raw_prompt_snapshot="fake prompt",
            token_usage={"prompt_tokens": 10, "completion_tokens": 5},
        )

    def stream_answer(
        self,
        *,
        query: str,
        contexts: Sequence[Any],
        enable_thinking: bool = False,
    ) -> Generator[tuple[str, str], None, None]:
        answer = self.generate_answer(
            query=query,
            contexts=contexts,
            enable_thinking=enable_thinking,
        )
        yield ("content", answer.content)

    def generate_direct_answer(self, *, query: str, enable_thinking: bool = False) -> LLMAnswer:
        self.requests.append(
            {
                "query": query,
                "contexts": [],
                "direct": True,
                "enable_thinking": enable_thinking,
            }
        )
        return LLMAnswer(
            content=f"Direct answer for {query}",
            model=self.model,
            prompt_version="direct-chat-v1",
            raw_prompt_snapshot="fake direct prompt",
            token_usage={"prompt_tokens": 3, "completion_tokens": 2},
        )

    def stream_direct_answer(
        self, *, query: str, enable_thinking: bool = False
    ) -> Generator[tuple[str, str], None, None]:
        answer = self.generate_direct_answer(
            query=query,
            enable_thinking=enable_thinking,
        )
        yield ("content", answer.content)


class FakeQueryRouter:
    def __init__(self) -> None:
        self.rule_based_router = RuleBasedQueryRouter()
        self.requests: list[str] = []

    def route(self, query: str) -> RouteDecision:
        self.requests.append(query)
        return self.rule_based_router.route(query)


class FakeKnowledgeSearchRouter:
    def __init__(self, decision: KnowledgeSearchDecision | None = None) -> None:
        self.decision = decision
        self.requests: list[str] = []

    def decide(self, query: str) -> KnowledgeSearchDecision:
        self.requests.append(query)
        return self.decision or KnowledgeSearchDecision(
            research_base=True,
            category="normal_rag",
            reason="test_default",
        )


class FakeImageDescriptionClient:
    enabled = True
    model = "fake-image-description"

    def __init__(self) -> None:
        self.requests: list[ImageDescriptionInput] = []

    def describe_image(self, image: ImageDescriptionInput) -> str:
        self.requests.append(image)
        return "用户上传图片描述"


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str | None]] = {}

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None,
        metadata: dict[str, str],
    ) -> None:
        self.objects[(bucket, key)] = (data, content_type)

    def get_object(self, *, bucket: str, key: str) -> bytes:
        return self.objects[(bucket, key)][0]


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
    knowledge_search_router: KnowledgeSearchRouterProtocol | None = None,
    query_router: QueryRouterProtocol | None = None,
    image_description_client: ImageDescriptionClientProtocol | None = None,
    object_storage: FakeObjectStorage | None = None,
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

    def override_query_router() -> QueryRouterProtocol:
        return query_router or FakeQueryRouter()

    def override_knowledge_search_router() -> KnowledgeSearchRouterProtocol:
        return knowledge_search_router or FakeKnowledgeSearchRouter()

    def override_image_description_client() -> ImageDescriptionClientProtocol:
        return image_description_client or FakeImageDescriptionClient()

    def override_object_storage() -> FakeObjectStorage:
        return object_storage or FakeObjectStorage()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_embedding_client] = override_embedding_client
    app.dependency_overrides[get_bm25_index_client] = override_bm25_index_client
    app.dependency_overrides[get_llm_client] = override_llm_client
    app.dependency_overrides[get_knowledge_search_router] = override_knowledge_search_router
    app.dependency_overrides[get_query_router] = override_query_router
    app.dependency_overrides[get_reranker_client] = override_reranker_client
    app.dependency_overrides[get_vector_index_client] = override_vector_index_client
    app.dependency_overrides[get_image_description_client] = override_image_description_client
    app.dependency_overrides[get_object_storage] = override_object_storage


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


def _seed_sectioned_chunks(
    session_factory: sessionmaker[Session],
) -> tuple[UUID, list[UUID]]:
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
            name="Section KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        db.add_all([reader, knowledge_base])
        db.flush()

        file = File(
            knowledge_base_id=knowledge_base.id,
            file_name="section.md",
            file_ext=".md",
            mime_type="text/markdown",
            file_size=1024,
            file_hash="s" * 64,
            storage_bucket="raw-files",
            storage_key="section",
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

        long_middle_content = "middle matched evidence " + ("x" * 360) + " complete ending"
        chunk_contents = [
            ("section opening context", ["Guide", "Install"], "md:Guide > Install#part-1"),
            (long_middle_content, ["Guide", "Install"], "md:Guide > Install#part-2"),
            ("section closing context", ["Guide", "Install"], "md:Guide > Install#part-3"),
            ("next section should not be included", ["Guide", "Usage"], "md:Guide > Usage"),
        ]
        chunks: list[ChunkMetadata] = []
        for index, (content, heading_path, source_locator) in enumerate(chunk_contents):
            chunk = ChunkMetadata(
                knowledge_base_id=knowledge_base.id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                chunk_index=index,
                content=content,
                content_hash=f"{index}" * 64,
                token_count=3,
                source_type="md",
                source_locator=source_locator,
                heading_path=heading_path,
                is_active=True,
                tsv=content,
            )
            db.add(chunk)
            chunks.append(chunk)
        db.commit()
        return knowledge_base.id, [chunk.id for chunk in chunks]


def _seed_visual_chunks(session_factory: sessionmaker[Session]) -> tuple[UUID, list[UUID]]:
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
            name="Visual KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        db.add_all([reader, knowledge_base])
        db.flush()

        file = File(
            knowledge_base_id=knowledge_base.id,
            file_name="architecture.pdf",
            file_ext=".pdf",
            mime_type="application/pdf",
            file_size=2048,
            file_hash="v" * 64,
            storage_bucket="raw-files",
            storage_key="architecture",
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

        chunks = [
            ChunkMetadata(
                knowledge_base_id=knowledge_base.id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                chunk_index=0,
                content="系统架构文字说明",
                content_hash="t" * 64,
                token_count=8,
                source_type="pdf",
                source_locator="pdf:p1",
                is_active=True,
                tsv="系统架构文字说明",
            ),
            ChunkMetadata(
                knowledge_base_id=knowledge_base.id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                chunk_index=1,
                content=(
                    "系统架构图 OCR：Frontend -> Backend -> Qdrant\n\n"
                    "![](images/architecture.png)\n"
                    "![](images/connection.jpg)"
                ),
                content_hash="i" * 64,
                token_count=12,
                source_type="pdf",
                source_locator="image:ocr-region-1",
                chunk_metadata={
                    "document_block_types": ["image_ocr"],
                },
                is_active=True,
                tsv="系统架构图 OCR Frontend Backend Qdrant",
            ),
        ]
        db.add_all(chunks)
        db.commit()
        return knowledge_base.id, [chunk.id for chunk in chunks]


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


def test_rule_direct_answer_skips_knowledge_base_retrieval() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_empty_knowledge_base(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(hits=[])
    reranker_client = FakeRerankerClient()
    bm25_index_client = FakeBM25IndexClient(enabled=True)
    llm_client = FakeLLMClient()
    query_router = FakeQueryRouter()
    knowledge_search_router = FakeKnowledgeSearchRouter(
        KnowledgeSearchDecision(
            research_base=False,
            category="identity",
            reason="rule_matched",
            direct_answer="我是你的知识库问答助手。",
        )
    )
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        llm_client,
        bm25_index_client,
        knowledge_search_router,
        query_router,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Direct Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "你是谁？", "stream": False},
        )
        assert message_response.status_code == 200
        assistant = message_response.json()["assistant_message"]
        assert assistant["content"] == "我是你的知识库问答助手。"
        assert assistant["citations"] == []
        assert embedding_client.requests == []
        assert vector_index_client.searches == []
        assert reranker_client.requests == []
        assert bm25_index_client.searches == []
        assert llm_client.requests == []
        assert query_router.requests == []

        with session_factory() as db:
            trace = db.scalar(select(MessageTrace))
        assert trace is not None
        assert trace.retrieved_chunk_ids == []
        assert trace.reranked_chunk_ids == []
        assert trace.final_context_chunk_ids == []
        assert trace.final_cited_chunk_ids == []
    finally:
        app.dependency_overrides.clear()


def test_overall_question_reads_knowledge_base_overall_without_similarity_search() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, _chunk_id = _seed_indexed_chunk(session_factory)
    overall_key = f"knowledge-bases/{knowledge_base_id}/overall.md"
    with session_factory() as db:
        knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
        assert knowledge_base is not None
        knowledge_base.settings = {
            "overall": {
                "bucket": "normalized-docs",
                "key": overall_key,
                "generated_at": "2026-06-17T00:00:00+00:00",
                "file_count": 1,
                "indexed_file_count": 1,
            }
        }
        file = db.scalar(select(File).where(File.knowledge_base_id == knowledge_base_id))
        assert file is not None
        parse_job = db.scalar(select(ParseJob).where(ParseJob.file_id == file.id))
        assert parse_job is not None
        file.latest_parse_job_id = parse_job.id
        db.add(
            DocumentSummary(
                knowledge_base_id=knowledge_base_id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                status="completed",
                summary="chat.txt 文档用于验证知识库对话和摘要返回。",
                chunk_prompt_version="chunk-knowledge-extraction-v1",
                document_prompt_version="document-summary-v1",
            )
        )
        db.add(
            KnowledgeBaseCommunitySummary(
                knowledge_base_id=knowledge_base_id,
                status="completed",
                summary="该社区汇总了聊天接口和知识库问答测试资料。",
                document_count=1,
                prompt_version="knowledge-base-community-summary-v1",
            )
        )
        db.commit()

    storage = FakeObjectStorage()
    storage.put_object(
        bucket="normalized-docs",
        key=overall_key,
        data=(
            "# Chat KB 知识库概览\n\n"
            "- 文件总数：1\n\n"
            "## 文件清单与大概描述\n\n"
            "### 1. chat.txt\n"
            "- 大概描述：用于聊天测试的资料。\n"
        ).encode(),
        content_type="text/markdown; charset=utf-8",
        metadata={},
    )
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(hits=[])
    reranker_client = FakeRerankerClient()
    bm25_index_client = FakeBM25IndexClient(enabled=True)
    llm_client = FakeLLMClient()
    knowledge_search_router = FakeKnowledgeSearchRouter(
        KnowledgeSearchDecision(
            research_base=False,
            category="knowledge_base_overall",
            reason="test_overall",
        )
    )
    query_router = FakeQueryRouter()
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        llm_client,
        bm25_index_client,
        knowledge_search_router,
        query_router,
        object_storage=storage,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Overall Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "当前知识库都包含什么数据？", "stream": False},
        )
        assert message_response.status_code == 200
        assistant = message_response.json()["assistant_message"]
        assert "Chat KB 知识库概览" in assistant["content"]
        assert "chat.txt" in assistant["content"]
        assert "该社区汇总了聊天接口和知识库问答测试资料。" in assistant["content"]
        assert "chat.txt 文档用于验证知识库对话和摘要返回。" in assistant["content"]
        assert assistant["citations"] == []
        assert embedding_client.requests == []
        assert vector_index_client.searches == []
        assert reranker_client.requests == []
        assert bm25_index_client.searches == []
        assert llm_client.requests == []
        assert knowledge_search_router.requests == ["当前知识库都包含什么数据？"]
        assert query_router.requests == []

        with session_factory() as db:
            trace = db.scalar(select(MessageTrace))
        assert trace is not None
        assert trace.chat_model == "knowledge-overall"
        assert trace.prompt_version == "knowledge-overall-v2"
        assert trace.retrieved_chunk_ids == []
    finally:
        app.dependency_overrides.clear()


def test_classifier_non_research_uses_direct_llm_without_retrieval() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_empty_knowledge_base(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(hits=[])
    reranker_client = FakeRerankerClient()
    llm_client = FakeLLMClient()
    knowledge_search_router = FakeKnowledgeSearchRouter(
        KnowledgeSearchDecision(
            research_base=False,
            category="llm_direct",
            reason="classifier",
        )
    )
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        llm_client,
        knowledge_search_router=knowledge_search_router,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Direct LLM"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "随便聊聊", "stream": False, "enable_thinking": True},
        )
        assert message_response.status_code == 200
        assistant = message_response.json()["assistant_message"]
        assert assistant["content"] == "Direct answer for 随便聊聊"
        assert assistant["citations"] == []
        assert llm_client.requests == [
            {
                "query": "随便聊聊",
                "contexts": [],
                "direct": True,
                "enable_thinking": True,
            }
        ]
        assert embedding_client.requests == []
        assert vector_index_client.searches == []
        assert reranker_client.requests == []
    finally:
        app.dependency_overrides.clear()


def test_mixed_question_uses_overall_context_and_normal_rag() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_id = _seed_indexed_chunk(session_factory)
    overall_key = f"knowledge-bases/{knowledge_base_id}/overall.md"
    with session_factory() as db:
        knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
        assert knowledge_base is not None
        knowledge_base.settings = {
            "overall": {
                "bucket": "normalized-docs",
                "key": overall_key,
                "generated_at": "2026-06-17T00:00:00+00:00",
                "file_count": 1,
                "indexed_file_count": 1,
            }
        }
        db.commit()

    storage = FakeObjectStorage()
    storage.put_object(
        bucket="normalized-docs",
        key=overall_key,
        data="# Chat KB 知识库概览\n\n- 文件总数：1\n".encode(),
        content_type="text/markdown; charset=utf-8",
        metadata={},
    )
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
    knowledge_search_router = FakeKnowledgeSearchRouter(
        KnowledgeSearchDecision(research_base=True, category="mixed", reason="test_mixed")
    )
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        llm_client,
        knowledge_search_router=knowledge_search_router,
        object_storage=storage,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Mixed Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={
                "content": "先说这个知识库有哪些资料，然后总结 demo answer",
                "stream": False,
            },
        )
        assert message_response.status_code == 200
        assistant = message_response.json()["assistant_message"]
        assert assistant["citations"][0]["chunk_id"] == str(chunk_id)
        assert len(llm_client.requests) == 1
        contexts = llm_client.requests[0]["contexts"]
        assert contexts[0].file_name == "knowledge-base-overall.md"
        assert "Chat KB 知识库概览" in contexts[0].excerpt
        assert contexts[1].chunk_id == str(chunk_id)
        assert embedding_client.requests
        assert vector_index_client.searches
        assert reranker_client.requests

        with session_factory() as db:
            trace = db.scalar(select(MessageTrace))
        assert trace is not None
        assert trace.final_context_chunk_ids is not None
        assert trace.final_cited_chunk_ids is not None
        assert trace.final_context_chunk_ids[0] == "00000000-0000-0000-0000-000000000000"
        assert trace.final_cited_chunk_ids == [str(chunk_id)]
    finally:
        app.dependency_overrides.clear()


def test_message_context_expands_matched_chunk_to_full_section() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_ids = _seed_sectioned_chunks(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_ids[1]),
                score=0.9,
                payload={
                    "chunk_id": str(chunk_ids[1]),
                    "knowledge_base_id": str(knowledge_base_id),
                },
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
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Section Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "matched evidence", "stream": False},
        )
        assert message_response.status_code == 200

        contexts = llm_client.requests[0]["contexts"]
        assert [context.chunk_id for context in contexts] == [
            str(chunk_ids[0]),
            str(chunk_ids[1]),
            str(chunk_ids[2]),
        ]
        assert contexts[1].excerpt.endswith("complete ending")
        assert all(
            "next section should not be included" not in context.excerpt for context in contexts
        )

        assistant = message_response.json()["assistant_message"]
        assert [citation["chunk_id"] for citation in assistant["citations"]] == [
            str(chunk_ids[0]),
            str(chunk_ids[1]),
            str(chunk_ids[2]),
        ]

        with session_factory() as db:
            trace = db.scalar(select(MessageTrace))
        assert trace is not None
        assert trace.retrieved_chunk_ids == [str(chunk_ids[1])]
        assert trace.final_context_chunk_ids == [
            str(chunk_ids[0]),
            str(chunk_ids[1]),
            str(chunk_ids[2]),
        ]
    finally:
        app.dependency_overrides.clear()


def test_visual_query_routes_image_context_and_returns_image_citation() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_ids = _seed_visual_chunks(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_ids[0]),
                score=0.9,
                payload={
                    "chunk_id": str(chunk_ids[0]),
                    "knowledge_base_id": str(knowledge_base_id),
                },
            ),
            VectorSearchHit(
                point_id=str(chunk_ids[1]),
                score=0.8,
                payload={
                    "chunk_id": str(chunk_ids[1]),
                    "knowledge_base_id": str(knowledge_base_id),
                },
            ),
        ]
    )
    reranker_client = FakeRerankerClient(scores=[0.9, 0.8])
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
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Visual Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "找一下系统架构图", "stream": False},
        )
        assert message_response.status_code == 200

        contexts = llm_client.requests[0]["contexts"]
        assert contexts[0].chunk_id == str(chunk_ids[1])
        assert contexts[0].modality == "image"
        assert contexts[0].image_url == (
            f"/api/v1/files/{contexts[0].file_id}/assets?path=images%2Farchitecture.png"
        )
        assert contexts[0].image_urls == [
            f"/api/v1/files/{contexts[0].file_id}/assets?path=images%2Farchitecture.png",
            f"/api/v1/files/{contexts[0].file_id}/assets?path=images%2Fconnection.jpg",
        ]
        assert "images/" not in contexts[0].excerpt

        citations = message_response.json()["assistant_message"]["citations"]
        image_citation = next(citation for citation in citations if citation["modality"] == "image")
        assert image_citation["chunk_id"] == str(chunk_ids[1])
        assert image_citation["image_url"].endswith("path=images%2Farchitecture.png")
        assert len(image_citation["image_urls"]) == 2
        assert "系统架构图 OCR" in image_citation["image_alt"]
        assert "images/" not in image_citation["excerpt"]
        assert "images/" not in image_citation["image_alt"]

        with session_factory() as db:
            image_row = db.scalar(
                select(MessageCitation).where(MessageCitation.chunk_id == chunk_ids[1])
            )
        assert image_row is not None
        assert image_row.allow_images is True
    finally:
        app.dependency_overrides.clear()


def test_image_attachment_is_saved_and_used_for_multimodal_search() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_ids = _seed_visual_chunks(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_ids[1]),
                score=0.95,
                payload={
                    "chunk_id": str(chunk_ids[1]),
                    "knowledge_base_id": str(knowledge_base_id),
                },
            )
        ]
    )
    reranker_client = FakeRerankerClient(scores=[0.9])
    llm_client = FakeLLMClient()
    object_storage = FakeObjectStorage()
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        llm_client,
        object_storage=object_storage,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")
        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Image Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        image_data_url = "data:image/png;base64,iVBORw0KGgo="
        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={
                "content": "查找与我这个图片比较相似的图",
                "stream": False,
                "attachments": [
                    {
                        "type": "image",
                        "file_name": "query.png",
                        "media_type": "image/png",
                        "data_url": image_data_url,
                    }
                ],
            },
        )
        assert message_response.status_code == 200
        body = message_response.json()
        assert body["user_message"]["attachments"][0]["file_name"] == "query.png"
        assert body["assistant_message"]["visual_result_mode"] == "gallery"
        assert any(search["modality"] == "image" for search in vector_index_client.searches)

        attachment_url = body["user_message"]["attachments"][0]["url"]
        asset_response = client.get(attachment_url, headers=_headers(token))
        assert asset_response.status_code == 200
        assert asset_response.content == b"\x89PNG\r\n\x1a\n"

        with session_factory() as db:
            attachment = db.scalar(select(MessageAttachment))
        assert attachment is not None
        assert attachment.file_name == "query.png"
    finally:
        app.dependency_overrides.clear()


def test_non_visual_query_suppresses_image_context_and_history_citation_images() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, chunk_ids = _seed_visual_chunks(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(
        hits=[
            VectorSearchHit(
                point_id=str(chunk_ids[1]),
                score=0.9,
                payload={
                    "chunk_id": str(chunk_ids[1]),
                    "knowledge_base_id": str(knowledge_base_id),
                },
            ),
        ]
    )
    reranker_client = FakeRerankerClient(scores=[0.9])
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
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Text Chat"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "系统架构怎么工作", "stream": False},
        )
        assert message_response.status_code == 200

        contexts = llm_client.requests[0]["contexts"]
        assert contexts[0].chunk_id == str(chunk_ids[1])
        assert contexts[0].modality == "text"
        assert contexts[0].image_url is None
        assert contexts[0].image_urls == []
        assert "images/" not in contexts[0].excerpt
        assert "![]" not in contexts[0].excerpt

        citations = message_response.json()["assistant_message"]["citations"]
        assert citations[0]["modality"] == "text"
        assert citations[0]["image_url"] is None
        assert citations[0]["image_urls"] == []
        assert "images/" not in citations[0]["excerpt"]

        detail_response = client.get(
            f"/api/v1/conversations/{conversation_id}",
            headers=_headers(token),
        )
        assert detail_response.status_code == 200
        assistant = next(
            message
            for message in detail_response.json()["messages"]
            if message["role"] == "assistant"
        )
        assert assistant["citations"][0]["image_url"] is None
        assert assistant["citations"][0]["image_urls"] == []
        assert "images/" not in assistant["citations"][0]["excerpt"]

        with session_factory() as db:
            citation = db.scalar(select(MessageCitation))
        assert citation is not None
        assert citation.allow_images is False
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
        assert text.index("event: message_created") < text.index("event: retrieval")
        assert text.index("event: retrieval") < text.index("event: token")
        assert text.index("event: token") < text.index("event: done")
        first_event_data = next(
            line.removeprefix("data: ").strip()
            for line in text.split("\n\n")[0].splitlines()
            if line.startswith("data:")
        )
        first_event = json.loads(first_event_data)
        assert first_event["user_message"]["content"] == "demo answer"
        assert first_event["assistant_message"]["content"] == ""
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


def test_stream_rule_direct_answer_returns_zero_retrieval_events() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_empty_knowledge_base(session_factory)
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(hits=[])
    reranker_client = FakeRerankerClient()
    knowledge_search_router = FakeKnowledgeSearchRouter(
        KnowledgeSearchDecision(
            research_base=False,
            category="greeting",
            reason="rule_matched",
            direct_answer="你好，我是知识库问答助手。",
        )
    )
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        knowledge_search_router=knowledge_search_router,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Stream Direct"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "你好", "stream": True},
        )
        assert message_response.status_code == 200
        text = message_response.text
        assert "event: message_created" in text
        assert "event: retrieval" in text
        assert '"retrieved_count": 0' in text
        assert '"reranked_count": 0' in text
        assert '"final_context_count": 0' in text
        assert "你好，我是知识库问答助手。" in text
        assert '"citations": []' in text
        assert embedding_client.requests == []
        assert vector_index_client.searches == []
        assert reranker_client.requests == []

        with session_factory() as db:
            citation = db.scalar(select(MessageCitation))
            trace = db.scalar(select(MessageTrace))
        assert citation is None
        assert trace is not None
        assert trace.final_context_chunk_ids == []
    finally:
        app.dependency_overrides.clear()


def test_stream_overall_question_reads_overall_without_similarity_search() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id, _chunk_id = _seed_indexed_chunk(session_factory)
    overall_key = f"knowledge-bases/{knowledge_base_id}/overall.md"
    with session_factory() as db:
        knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
        assert knowledge_base is not None
        knowledge_base.settings = {
            "overall": {
                "bucket": "normalized-docs",
                "key": overall_key,
                "generated_at": "2026-06-17T00:00:00+00:00",
                "file_count": 1,
                "indexed_file_count": 1,
            }
        }
        db.commit()

    storage = FakeObjectStorage()
    storage.put_object(
        bucket="normalized-docs",
        key=overall_key,
        data="# Chat KB 知识库概览\n\n- 文件总数：1\n".encode(),
        content_type="text/markdown; charset=utf-8",
        metadata={},
    )
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient(hits=[])
    reranker_client = FakeRerankerClient()
    bm25_index_client = FakeBM25IndexClient(enabled=True)
    knowledge_search_router = FakeKnowledgeSearchRouter(
        KnowledgeSearchDecision(
            research_base=False,
            category="knowledge_base_overall",
            reason="test_overall",
        )
    )
    query_router = FakeQueryRouter()
    _install_overrides(
        session_factory,
        embedding_client,
        vector_index_client,
        reranker_client,
        bm25_index_client=bm25_index_client,
        knowledge_search_router=knowledge_search_router,
        query_router=query_router,
        object_storage=storage,
    )
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        create_response = client.post(
            "/api/v1/conversations",
            headers=_headers(token),
            json={"knowledge_base_id": str(knowledge_base_id), "title": "Stream Overall"},
        )
        assert create_response.status_code == 201
        conversation_id = create_response.json()["id"]

        message_response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            headers=_headers(token),
            json={"content": "这个知识库有哪些资料？", "stream": True},
        )
        assert message_response.status_code == 200
        text = message_response.text
        assert "event: retrieval" in text
        assert '"retrieved_count": 0' in text
        assert "Chat KB 知识库概览" in text
        assert '"citations": []' in text
        streamed_tokens = []
        for event_block in text.split("\n\n"):
            if not event_block.startswith("event: token\n"):
                continue
            data_line = next(line for line in event_block.splitlines() if line.startswith("data: "))
            streamed_tokens.append(json.loads(data_line.removeprefix("data: "))["text"])
        streamed_answer = "".join(streamed_tokens)
        assert "\n\n## 知识库社区摘要\n\n" in streamed_answer
        assert "\n\n## 各文档摘要\n\n" in streamed_answer
        assert "\n\n### 1. chat.txt\n\n" in streamed_answer
        assert embedding_client.requests == []
        assert vector_index_client.searches == []
        assert reranker_client.requests == []
        assert bm25_index_client.searches == []
        assert knowledge_search_router.requests == ["这个知识库有哪些资料？"]
        assert query_router.requests == []

        with session_factory() as db:
            trace = db.scalar(select(MessageTrace))
            assistant_message = db.scalar(
                select(Message)
                .where(Message.role == "assistant")
                .order_by(Message.created_at.desc())
            )
        assert trace is not None
        assert assistant_message is not None
        assert "\n\n### 1. chat.txt\n\n" in assistant_message.content
        assert trace.chat_model == "knowledge-overall"
        assert trace.prompt_version == "knowledge-overall-v2"
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
