from collections.abc import Generator, Sequence
from datetime import UTC, datetime
from io import BytesIO
from typing import Any, cast
from uuid import UUID, uuid4
from zipfile import ZipFile

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.files import (
    get_bm25_index_client,
    get_embedding_client,
    get_image_description_client,
    get_mineru_client,
    get_object_storage,
    get_vector_index_client,
)
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db, get_session_factory
from app.main import app
from app.models import (
    AuditLog,
    ChunkKnowledgeExtraction,
    ChunkMetadata,
    DocumentSummary,
    DocumentBlock,
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
from app.services.bm25_index import BM25ChunkDocument, BM25IndexClientProtocol
from app.services.chunks import build_chunk_drafts, build_chunk_response
from app.services.document_blocks import extract_blocks_from_zip
from app.services.document_summary_llm import CHUNK_PROMPT_VERSION, DOCUMENT_PROMPT_VERSION
from app.services.embedding import EmbeddingClientProtocol
from app.services.image_descriptions import ImageDescriptionClientProtocol, ImageDescriptionInput
from app.services.mineru import MineruClient, MineruSubmission
from app.services.object_storage import ObjectStorage
from app.services.vector_index import VectorIndexClientProtocol, VectorSearchHit


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


class FakeMineruClient:
    def __init__(
        self,
        *,
        result_state: str = "done",
        full_zip_url: str | None = "https://example.local/mineru-full.zip",
        error_message: str = "MinerU parse failed.",
        submit_error_message: str | None = None,
        result_zip: bytes | None = None,
    ) -> None:
        self.result_state = result_state
        self.full_zip_url = full_zip_url
        self.error_message = error_message
        self.submit_error_message = submit_error_message
        self.result_zip = result_zip
        self.submissions: list[dict[str, object]] = []

    def submit_file(
        self,
        *,
        file_name: str,
        data_id: str,
        content: bytes,
    ) -> MineruSubmission:
        if self.submit_error_message is not None:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message=self.submit_error_message,
                status_code=503,
            )
        self.submissions.append(
            {
                "file_name": file_name,
                "data_id": data_id,
                "content": content,
            }
        )
        return MineruSubmission(
            batch_id="batch-001",
            data_id=data_id,
            raw_response={"code": 0, "data": {"batch_id": "batch-001", "file_urls": ["fake"]}},
        )

    def get_batch_result(self, *, batch_id: str) -> dict[str, object]:
        assert batch_id == "batch-001"
        result_item: dict[str, object] = {
            "data_id": str(self.submissions[-1]["data_id"]),
            "state": self.result_state,
        }
        if self.full_zip_url is not None:
            result_item["full_zip_url"] = self.full_zip_url
        if self.result_state in {"failed", "error"}:
            result_item["err_msg"] = self.error_message
        return {
            "code": 0,
            "data": {"extract_result": [result_item]},
        }

    def download_result(self, *, url: str) -> bytes:
        assert url == self.full_zip_url
        return self.result_zip or build_test_mineru_zip()


def build_test_mineru_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("result.md", "# Title\n\nFirst paragraph.\n\nSecond paragraph.")
        archive.writestr(
            "blocks.json",
            '[{"type":"text","content":"JSON block","page_number":2}]',
        )
    return buffer.getvalue()


def build_rich_test_mineru_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "document/result.md",
            (
                "# Chapter 1\n\n"
                "## Section A\n\n"
                "Paragraph under section.\n\n"
                "| Metric | Value |\n"
                "| --- | --- |\n"
                "| Coverage | High |"
            ),
        )
        archive.writestr(
            "layout.json",
            (
                '{"pages":[{"page_idx":0,"blocks":['
                '{"type":"text","text":"PDF page text"},'
                '{"type":"table","table_body":"| A | B |\\\\n| --- | --- |\\\\n| 1 | 2 |"},'
                '{"type":"image","text":"OCR figure text","region_index":3}'
                "]}]}"
            ),
        )
    return buffer.getvalue()


def build_image_asset_mineru_zip() -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "layout.json",
            (
                '{"pages":[{"page_idx":0,"blocks":['
                '{"type":"image","text":"系统架构图 OCR",'
                '"asset_path":"images/architecture.png","region_index":1}'
                "]}]}"
            ),
        )
        archive.writestr("images/architecture.png", b"fake-png")
    return buffer.getvalue()


def test_mineru_zip_normalization_preserves_heading_table_and_ocr_metadata() -> None:
    normalized_blocks = extract_blocks_from_zip(build_rich_test_mineru_zip())

    assert [block.block_type for block in normalized_blocks] == [
        "heading",
        "heading",
        "text",
        "table",
        "text",
        "table",
        "image_ocr",
    ]
    assert normalized_blocks[1].metadata["heading_path"] == ["Chapter 1", "Section A"]
    assert normalized_blocks[2].metadata["heading_path"] == ["Chapter 1", "Section A"]
    assert normalized_blocks[4].page_number == 1
    assert normalized_blocks[5].page_number == 1
    assert normalized_blocks[6].metadata["source_locator"] == "image:ocr-region-3"

    blocks = [
        DocumentBlock(
            block_index=index,
            block_type=block.block_type,
            content=block.content,
            page_number=block.page_number,
            slide_number=block.slide_number,
            sheet_name=block.sheet_name,
            row_start=block.row_start,
            row_end=block.row_end,
            bbox=block.bbox,
            block_metadata=block.metadata,
        )
        for index, block in enumerate(normalized_blocks)
    ]

    markdown_file = File(file_ext=".md")
    markdown_drafts = build_chunk_drafts(blocks=blocks[:4], file=markdown_file)
    assert markdown_drafts[0].source_locator == "md:Chapter 1"
    assert markdown_drafts[1].source_locator == "md:Chapter 1 > Section A"
    assert markdown_drafts[2].metadata["split_reason"] == "table"

    image_file = File(file_ext=".png")
    image_drafts = build_chunk_drafts(blocks=[blocks[6]], file=image_file)
    assert image_drafts[0].source_locator == "image:ocr-region-3"


def test_chunk_debug_response_exposes_image_table_and_metadata_fields() -> None:
    knowledge_base_id = uuid4()
    file_id = uuid4()
    parse_job_id = uuid4()
    created_at = datetime.now(UTC)
    file = File(id=file_id, file_name="architecture.pdf")
    image_chunk = ChunkMetadata(
        id=uuid4(),
        knowledge_base_id=knowledge_base_id,
        file_id=file_id,
        parse_job_id=parse_job_id,
        chunk_index=1,
        content="系统架构图 OCR",
        description="图片展示系统架构图。",
        content_hash="a" * 64,
        token_count=8,
        source_type="pdf",
        source_locator="pdf:p1",
        chunk_metadata={
            "asset_path": "images/diagram.png",
            "document_block_types": ["image_ocr"],
            "description_status": "generated",
        },
        is_active=True,
        created_at=created_at,
    )
    table_chunk = ChunkMetadata(
        id=uuid4(),
        knowledge_base_id=knowledge_base_id,
        file_id=file_id,
        parse_job_id=parse_job_id,
        chunk_index=2,
        content="| A | B |\n| --- | --- |\n| 1 | 2 |",
        content_hash="b" * 64,
        token_count=12,
        source_type="pdf",
        source_locator="pdf:p2",
        chunk_metadata={"document_block_types": ["table"], "split_reason": "table"},
        is_active=True,
        created_at=created_at,
    )
    text_chunk = ChunkMetadata(
        id=uuid4(),
        knowledge_base_id=knowledge_base_id,
        file_id=file_id,
        parse_job_id=parse_job_id,
        chunk_index=3,
        content="Plain text",
        content_hash="c" * 64,
        token_count=2,
        source_type="pdf",
        source_locator="pdf:p3",
        chunk_metadata={},
        is_active=True,
        created_at=created_at,
    )

    image_response = build_chunk_response(image_chunk, file=file)
    table_response = build_chunk_response(table_chunk, file=file)
    text_response = build_chunk_response(text_chunk, file=file)

    assert image_response.modality == "image"
    assert image_response.description == "图片展示系统架构图。"
    assert image_response.asset_paths == ["images/diagram.png"]
    assert image_response.document_block_types == ["image_ocr"]
    assert image_response.metadata["description_status"] == "generated"
    assert image_response.image_url is not None
    assert image_response.image_url.endswith("path=images%2Fdiagram.png")
    assert image_response.image_urls == [image_response.image_url]
    assert image_response.image_alt == "图片展示系统架构图。"

    assert table_response.modality == "table"
    assert table_response.image_url is None
    assert table_response.image_urls == []
    assert table_response.asset_paths == []
    assert table_response.document_block_types == ["table"]
    assert table_response.metadata["split_reason"] == "table"

    assert text_response.modality == "text"
    assert text_response.description is None
    assert text_response.image_url is None
    assert text_response.asset_paths == []
    assert text_response.document_block_types == []


class FakeEmbeddingClient:
    model = "fake-bge-m3"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.requests.append(list(texts))
        return [[float(index + 1), float(len(text))] for index, text in enumerate(texts)]


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
        point_id_set = set(point_ids)
        for point in self.points:
            if str(point.get("id")) not in point_id_set:
                continue
            payload = point.get("payload")
            if isinstance(payload, dict):
                payload["is_active"] = False

    def search_points(
        self,
        *,
        vector: list[float],
        knowledge_base_id: str,
        limit: int,
    ) -> list[VectorSearchHit]:
        return []


class FakeBM25IndexClient:
    enabled = True
    provider = "fake-bm25"
    index_name = "chunks_bm25"

    def __init__(self) -> None:
        self.ensure_calls = 0
        self.documents: list[BM25ChunkDocument] = []
        self.deactivated_chunk_ids: list[str] = []

    def ensure_index(self) -> None:
        self.ensure_calls += 1

    def upsert_chunks(self, *, documents: list[BM25ChunkDocument]) -> None:
        self.documents.extend(documents)

    def deactivate_chunks(self, *, chunk_ids: list[str]) -> None:
        self.deactivated_chunk_ids.extend(chunk_ids)

    def search(
        self,
        *,
        query: str,
        knowledge_base_id: str,
        limit: int,
    ) -> list[Any]:
        return []


class FakeImageDescriptionClient:
    enabled = True
    model = "qwen3.6-flash"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.requests: list[ImageDescriptionInput] = []

    def describe_image(self, image: ImageDescriptionInput) -> str:
        self.requests.append(image)
        if self.fail:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="vision unavailable",
                status_code=502,
            )
        return "图片展示系统架构图，包含前端、后端和向量库之间的连接。"


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
    storage: FakeObjectStorage,
    mineru_client: FakeMineruClient | None = None,
    embedding_client: FakeEmbeddingClient | None = None,
    vector_index_client: FakeVectorIndexClient | None = None,
    bm25_index_client: FakeBM25IndexClient | None = None,
    image_description_client: FakeImageDescriptionClient | None = None,
) -> None:
    bm25_index_client = bm25_index_client or FakeBM25IndexClient()

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    def override_storage() -> ObjectStorage:
        return storage

    def override_session_factory() -> sessionmaker[Session]:
        return session_factory

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_session_factory] = override_session_factory
    app.dependency_overrides[get_object_storage] = override_storage
    if mineru_client is not None:

        def override_mineru_client() -> MineruClient:
            return mineru_client

        app.dependency_overrides[get_mineru_client] = override_mineru_client
    if embedding_client is not None:

        def override_embedding_client() -> EmbeddingClientProtocol:
            return embedding_client

        app.dependency_overrides[get_embedding_client] = override_embedding_client
    if vector_index_client is not None:

        def override_vector_index_client() -> VectorIndexClientProtocol:
            return vector_index_client

        app.dependency_overrides[get_vector_index_client] = override_vector_index_client

    if image_description_client is not None:

        def override_image_description_client() -> ImageDescriptionClientProtocol:
            return image_description_client

        app.dependency_overrides[get_image_description_client] = override_image_description_client

    def override_bm25_index_client() -> BM25IndexClientProtocol:
        return bm25_index_client

    app.dependency_overrides[get_bm25_index_client] = override_bm25_index_client


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _seed_admin_user_and_kb(session_factory: sessionmaker[Session]) -> UUID:
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
        knowledge_base = KnowledgeBase(
            name="Files KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        db.add_all([user, knowledge_base])
        db.commit()
        return knowledge_base.id


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_read_retry_and_debug_document_summary() -> None:
    session_factory = _make_session_factory()
    storage = FakeObjectStorage()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    _install_overrides(session_factory, storage)
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        file = File(
            knowledge_base_id=knowledge_base_id,
            file_name="summary.pdf",
            file_ext=".pdf",
            mime_type="application/pdf",
            file_size=100,
            file_hash="d" * 64,
            storage_bucket="raw-files",
            storage_key="summary.pdf",
            status=FileStatus.INDEXED.value,
            created_by=admin.id,
        )
        db.add(file)
        db.flush()
        parse_job = ParseJob(
            file_id=file.id,
            knowledge_base_id=knowledge_base_id,
            status=ParseJobStatus.INDEXED.value,
            progress=100,
            created_by=admin.id,
        )
        db.add(parse_job)
        db.flush()
        file.latest_parse_job_id = parse_job.id
        chunk = ChunkMetadata(
            knowledge_base_id=knowledge_base_id,
            file_id=file.id,
            parse_job_id=parse_job.id,
            chunk_index=0,
            content="文档要求所有操作保留审计记录。",
            content_hash="e" * 64,
            token_count=15,
            source_type="pdf",
            source_locator="pdf:p1",
            chunk_metadata={"document_block_types": ["text"]},
            is_active=True,
        )
        db.add(chunk)
        db.flush()
        extraction_payload = {
            "chunk_id": str(chunk.id),
            "semantic_role": "REQUIREMENT",
            "short_summary": "文档要求所有操作保留审计记录。",
            "topics": ["审计"],
            "keywords": ["操作", "审计记录"],
            "entities": [],
            "assertions": [
                {
                    "statement": "所有操作必须保留审计记录。",
                    "statement_type": "REQUIREMENT",
                    "subject": "所有操作",
                    "predicate": "必须保留",
                    "object": "审计记录",
                    "conditions": [],
                    "time_scope": None,
                    "polarity": "POSITIVE",
                    "certainty": "HIGH",
                    "evidence_text": "要求所有操作保留审计记录",
                }
            ],
            "importance": 0.9,
            "quality_flags": ["NONE"],
        }
        db.add(
            ChunkKnowledgeExtraction(
                chunk_id=chunk.id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                status="completed",
                extraction=extraction_payload,
                short_summary=extraction_payload["short_summary"],
                model_name="test-model",
                prompt_version=CHUNK_PROMPT_VERSION,
                attempt_count=1,
            )
        )
        db.add(
            DocumentSummary(
                knowledge_base_id=knowledge_base_id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                status="completed",
                priority=10,
                summary="该文档规定所有操作需要保留审计记录。",
                chunk_total=1,
                chunk_completed=1,
                chunk_succeeded=1,
                chunk_failed=0,
                failed_chunk_ids=[],
                model_name="test-model",
                chunk_prompt_version=CHUNK_PROMPT_VERSION,
                document_prompt_version=DOCUMENT_PROMPT_VERSION,
            )
        )
        db.commit()
        file_id = file.id
        chunk_id = chunk.id

    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        user_token = _login(client, "reader", "ReaderPassword123")

        forbidden = client.get(
            f"/api/v1/files/{file_id}/summary",
            headers=_headers(user_token),
        )
        assert forbidden.status_code == 403

        response = client.get(
            f"/api/v1/files/{file_id}/summary",
            headers=_headers(admin_token),
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["summary"] == "该文档规定所有操作需要保留审计记录。"

        chunks_response = client.get(
            f"/api/v1/files/{file_id}/chunks",
            headers=_headers(admin_token),
        )
        assert chunks_response.status_code == 200
        extraction = chunks_response.json()["items"][0]["knowledge_extraction"]
        assert extraction["extraction"]["chunk_id"] == str(chunk_id)
        assert extraction["extraction"]["semantic_role"] == "REQUIREMENT"

        retry_response = client.post(
            f"/api/v1/files/{file_id}/summary/retry",
            headers=_headers(admin_token),
            json={"force": True},
        )
        assert retry_response.status_code == 202
        assert retry_response.json()["status"] == "pending"
        assert retry_response.json()["chunk_completed"] == 0
    finally:
        app.dependency_overrides.clear()


def test_admin_can_upload_file_and_read_list_status_and_minio_object() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(result_state="running")
    _install_overrides(session_factory, storage, mineru_client)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")

        response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("report.txt", b"hello knowledge", "text/plain"))],
        )

        assert response.status_code == 202
        body = response.json()
        assert body["warnings"] == []
        uploaded = body["uploaded"][0]
        file_body = uploaded["file"]
        parse_job_body = uploaded["parse_job"]
        assert file_body["file_name"] == "report.txt"
        assert file_body["file_ext"] == ".txt"
        assert file_body["status"] == "queued"
        assert file_body["latest_parse_job_id"] == parse_job_body["id"]
        assert parse_job_body["status"] == "queued"
        assert parse_job_body["progress"] == 0

        with session_factory() as db:
            stored_file = db.get(File, UUID(file_body["id"]))
            parse_job = db.get(ParseJob, UUID(parse_job_body["id"]))
            upload_audit = db.scalar(select(AuditLog).where(AuditLog.action == "upload_file"))
        assert stored_file is not None
        assert parse_job is not None
        assert upload_audit is not None
        assert (stored_file.storage_bucket, stored_file.storage_key) in storage.objects
        stored_object = storage.objects[(stored_file.storage_bucket, stored_file.storage_key)]
        assert stored_object["data"] == b"hello knowledge"
        assert stored_object["metadata"] == {
            "file_id": file_body["id"],
            "knowledge_base_id": str(knowledge_base_id),
            "file_hash": file_body["file_hash"],
        }

        list_response = client.get(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files?keyword=report",
            headers=_headers(admin_token),
        )
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["id"] == file_body["id"]

        status_response = client.get(
            f"/api/v1/files/{file_body['id']}/status",
            headers=_headers(admin_token),
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["file_status"] == "processing"
        assert status_body["latest_parse_job"]["id"] == parse_job_body["id"]
        assert status_body["latest_parse_job"]["status"] == "parsing"
        assert status_body["latest_parse_job"]["progress"] == 10
        assert mineru_client.submissions[0]["file_name"] == "report.txt"
    finally:
        app.dependency_overrides.clear()


def test_user_cannot_upload_file() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    _install_overrides(session_factory, storage)
    try:
        client = TestClient(app)
        user_token = _login(client, "reader", "ReaderPassword123")

        response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(user_token),
            files=[("files", ("report.txt", b"hello", "text/plain"))],
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert storage.objects == {}
    finally:
        app.dependency_overrides.clear()


def test_user_can_read_parsed_image_asset_with_auth() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    with session_factory() as db:
        admin = db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        file = File(
            knowledge_base_id=knowledge_base_id,
            file_name="architecture.pdf",
            file_ext=".pdf",
            mime_type="application/pdf",
            file_size=1024,
            file_hash="a" * 64,
            storage_bucket="raw-files",
            storage_key="architecture.pdf",
            status=FileStatus.INDEXED.value,
            created_by=admin.id,
        )
        db.add(file)
        db.flush()
        parse_job = ParseJob(
            file_id=file.id,
            knowledge_base_id=knowledge_base_id,
            status=ParseJobStatus.INDEXED.value,
            progress=100,
            logs={
                "parsed_result": {
                    "bucket": "parsed-results",
                    "key": "parsed/architecture.zip",
                    "content_type": "application/zip",
                }
            },
            created_by=admin.id,
        )
        db.add(parse_job)
        db.flush()
        file.latest_parse_job_id = parse_job.id
        file_id = file.id
        db.commit()

    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("images/architecture.png", b"fake-png")
    storage.put_object(
        bucket="parsed-results",
        key="parsed/architecture.zip",
        data=buffer.getvalue(),
        content_type="application/zip",
        metadata={},
    )
    _install_overrides(session_factory, storage)
    try:
        client = TestClient(app)
        token = _login(client, "reader", "ReaderPassword123")

        response = client.get(
            f"/api/v1/files/{file_id}/assets?path=images%2Farchitecture.png",
            headers=_headers(token),
        )

        assert response.status_code == 200
        assert response.content == b"fake-png"
        assert response.headers["content-type"].startswith("image/png")
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_too_large_file_and_unsupported_extension() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    _install_overrides(session_factory, storage)
    settings = get_settings()
    original_max_file_size_mb = settings.max_file_size_mb
    settings.max_file_size_mb = 0
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")

        too_large = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("large.txt", b"x", "text/plain"))],
        )
        assert too_large.status_code == 413
        assert too_large.json()["error"]["code"] == "FILE_TOO_LARGE"

        settings.max_file_size_mb = original_max_file_size_mb
        unsupported = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("legacy.doc", b"x", "application/msword"))],
        )
        assert unsupported.status_code == 415
        assert unsupported.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
    finally:
        settings.max_file_size_mb = original_max_file_size_mb
        app.dependency_overrides.clear()


def test_upload_rejects_duplicate_file_name_and_duplicate_hash_without_force() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    _install_overrides(session_factory, storage)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_url = f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload"

        first = client.post(
            upload_url,
            headers=_headers(admin_token),
            files=[("files", ("report.txt", b"same content", "text/plain"))],
        )
        assert first.status_code == 202

        duplicate_name = client.post(
            upload_url,
            headers=_headers(admin_token),
            files=[("files", ("report.txt", b"different content", "text/plain"))],
        )
        assert duplicate_name.status_code == 409
        assert duplicate_name.json()["error"]["code"] == "DUPLICATE_FILE_NAME"

        duplicate_hash = client.post(
            upload_url,
            headers=_headers(admin_token),
            files=[("files", ("copy.txt", b"same content", "text/plain"))],
        )
        assert duplicate_hash.status_code == 409
        error = duplicate_hash.json()["error"]
        assert error["code"] == "DUPLICATE_FILE_HASH"
        assert error["details"]["can_force_upload"] is True
        assert error["details"]["duplicates"][0]["incoming_file_name"] == "copy.txt"
        assert error["details"]["duplicates"][0]["existing_file_name"] == "report.txt"
    finally:
        app.dependency_overrides.clear()


def test_force_upload_allows_duplicate_hash_and_delete_soft_deletes_with_audit() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    _install_overrides(session_factory, storage)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_url = f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload"

        first = client.post(
            upload_url,
            headers=_headers(admin_token),
            files=[("files", ("report.txt", b"same content", "text/plain"))],
        )
        assert first.status_code == 202

        forced = client.post(
            upload_url,
            headers=_headers(admin_token),
            data={"force": "true"},
            files=[("files", ("copy.txt", b"same content", "text/plain"))],
        )
        assert forced.status_code == 202
        forced_file_id = forced.json()["uploaded"][0]["file"]["id"]

        delete_response = client.delete(
            f"/api/v1/files/{forced_file_id}",
            headers=_headers(admin_token),
        )
        assert delete_response.status_code == 204

        get_deleted = client.get(f"/api/v1/files/{forced_file_id}", headers=_headers(admin_token))
        assert get_deleted.status_code == 404

        with session_factory() as db:
            deleted_file = db.get(File, UUID(forced_file_id))
            delete_audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.action == "delete_file",
                    AuditLog.resource_id == UUID(forced_file_id),
                )
            )
        assert deleted_file is not None
        assert deleted_file.status == "deleted"
        assert deleted_file.deleted_at is not None
        assert delete_audit is not None
    finally:
        app.dependency_overrides.clear()


def test_retry_parse_submits_file_to_mineru_and_status_poll_saves_result() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(result_state="done")
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient()
    bm25_index_client = FakeBM25IndexClient()
    _install_overrides(
        session_factory,
        storage,
        mineru_client,
        embedding_client,
        vector_index_client,
        bm25_index_client,
    )
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("report.txt", b"parse me", "text/plain"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]
        mineru_client.submissions.clear()
        embedding_client.requests.clear()
        vector_index_client.vector_sizes.clear()
        vector_index_client.points.clear()
        bm25_index_client.ensure_calls = 0
        bm25_index_client.documents.clear()

        retry_response = client.post(
            f"/api/v1/files/{file_id}/retry-parse",
            headers=_headers(admin_token),
        )
        assert retry_response.status_code == 202
        parse_job_body = retry_response.json()
        assert parse_job_body["status"] == "queued"
        assert parse_job_body["progress"] == 0
        assert parse_job_body["error_code"] is None
        assert parse_job_body["logs"]["provider"] == "mineru"
        assert parse_job_body["logs"]["mode"] == "api_v4_file_urls_batch"
        assert mineru_client.submissions == [
            {
                "file_name": "report.txt",
                "data_id": parse_job_body["id"],
                "content": b"parse me",
            }
        ]

        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["file_status"] == "indexed"
        assert status_body["latest_parse_job"]["id"] == parse_job_body["id"]
        assert status_body["latest_parse_job"]["status"] == "indexed"
        assert status_body["latest_parse_job"]["progress"] == 100
        assert status_body["latest_parse_job"]["error_code"] is None
        assert status_body["latest_parse_job"]["logs"]["mineru_latest_state"] == "done"
        assert status_body["latest_parse_job"]["logs"]["parsed_result"]["bucket"] == (
            "parsed-results"
        )

        with session_factory() as db:
            parse_job = db.get(ParseJob, UUID(parse_job_body["id"]))
            chunks = db.scalars(
                select(ChunkMetadata)
                .where(ChunkMetadata.parse_job_id == UUID(parse_job_body["id"]))
                .order_by(ChunkMetadata.chunk_index)
            ).all()
        assert parse_job is not None
        assert parse_job.logs is not None
        assert parse_job.logs["chunking"]["chunk_count"] == 2
        assert parse_job.logs["chunking"]["strategy"] == "heading_aware_recursive"
        assert parse_job.logs["indexing"]["chunk_count"] == 2
        assert parse_job.logs["indexing"]["embedding_model"] == "fake-bge-m3"
        assert parse_job.logs["indexing"]["qdrant_collection"] == "chunks"
        assert parse_job.logs["indexing"]["bm25_provider"] == "fake-bm25"
        assert parse_job.logs["indexing"]["bm25_index"] == "chunks_bm25"
        assert parse_job.logs["indexing"]["vector_size"] == 2
        parsed_result = cast(dict[str, Any], parse_job.logs["parsed_result"])
        assert parsed_result["bucket"] == "parsed-results"
        parsed_key = str(parsed_result["key"])
        assert ("parsed-results", parsed_key) in storage.objects
        stored_result = storage.objects[("parsed-results", parsed_key)]
        with ZipFile(BytesIO(cast(bytes, stored_result["data"]))) as archive:
            assert archive.read("result.md").decode("utf-8") == (
                "# Title\n\nFirst paragraph.\n\nSecond paragraph."
            )
        stored_metadata = cast(dict[str, str], stored_result["metadata"])
        assert stored_metadata["parse_job_id"] == parse_job_body["id"]
        assert len(chunks) == 2
        assert chunks[0].content == "JSON block"
        assert chunks[0].source_locator == "txt:p2"
        assert chunks[0].content_hash
        assert chunks[0].token_count == 2
        assert chunks[0].is_active is True
        assert chunks[0].tsv == "JSON block"
        assert chunks[1].content == "# Title\n\nFirst paragraph.\n\nSecond paragraph."
        assert chunks[1].heading_path == ["Title"]
        assert chunks[1].source_locator == "txt:block-2"
        assert embedding_client.requests == [
            ["JSON block", "# Title\n\nFirst paragraph.\n\nSecond paragraph."]
        ]
        assert vector_index_client.vector_sizes == [2]
        assert len(vector_index_client.points) == 2
        first_point = vector_index_client.points[0]
        assert first_point["id"] == str(chunks[0].id)
        assert first_point["vector"] == [1.0, 10.0]
        first_payload = cast(dict[str, Any], first_point["payload"])
        assert first_payload["chunk_id"] == str(chunks[0].id)
        assert first_payload["knowledge_base_id"] == str(knowledge_base_id)
        assert first_payload["file_id"] == file_id
        assert first_payload["parse_job_id"] == parse_job_body["id"]
        assert first_payload["file_name"] == "report.txt"
        assert first_payload["source_type"] == "txt"
        assert first_payload["source_locator"] == "txt:p2"
        assert first_payload["is_active"] is True
        assert first_payload["content_hash"] == chunks[0].content_hash
        assert bm25_index_client.ensure_calls == 1
        assert len(bm25_index_client.documents) == 2
        first_bm25_document = bm25_index_client.documents[0]
        assert first_bm25_document.chunk_id == str(chunks[0].id)
        assert first_bm25_document.knowledge_base_id == str(knowledge_base_id)
        assert first_bm25_document.file_id == file_id
        assert first_bm25_document.parse_job_id == parse_job_body["id"]
        assert first_bm25_document.file_name == "report.txt"
        assert first_bm25_document.content == "JSON block"
        assert first_bm25_document.source_locator == "txt:p2"
        assert first_bm25_document.source_type == "txt"
        assert first_bm25_document.is_active is True

        chunks_response = client.get(
            f"/api/v1/files/{file_id}/chunks",
            headers=_headers(admin_token),
        )
        assert chunks_response.status_code == 200
        chunks_body = chunks_response.json()
        assert chunks_body["total"] == 2
        contents = [item["content"] for item in chunks_body["items"]]
        assert "# Title\n\nFirst paragraph.\n\nSecond paragraph." in contents
        assert "JSON block" in contents
        json_block = next(item for item in chunks_body["items"] if item["content"] == "JSON block")
        assert json_block["source_locator"] == "txt:p2"
    finally:
        app.dependency_overrides.clear()


def test_image_asset_chunk_gets_description_before_indexing() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(
        result_state="done",
        result_zip=build_image_asset_mineru_zip(),
    )
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient()
    bm25_index_client = FakeBM25IndexClient()
    image_description_client = FakeImageDescriptionClient()
    _install_overrides(
        session_factory,
        storage,
        mineru_client,
        embedding_client,
        vector_index_client,
        bm25_index_client,
        image_description_client,
    )
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")

        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("architecture.pdf", b"parse me", "application/pdf"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]
        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )

        assert status_response.status_code == 200
        assert status_response.json()["file_status"] == "indexed"
        with session_factory() as db:
            chunk = db.scalar(select(ChunkMetadata).where(ChunkMetadata.file_id == UUID(file_id)))
            parse_job = db.get(ParseJob, UUID(status_response.json()["latest_parse_job"]["id"]))
        assert chunk is not None
        assert parse_job is not None
        assert chunk.description == "图片展示系统架构图，包含前端、后端和向量库之间的连接。"
        assert chunk.chunk_metadata is not None
        assert chunk.chunk_metadata["asset_path"] == "images/architecture.png"
        assert chunk.chunk_metadata["description_status"] == "generated"
        assert chunk.chunk_metadata["description_model"] == "qwen3.6-flash"
        assert image_description_client.requests[0].media_type == "image/png"
        assert embedding_client.requests == [
            [
                "图片展示系统架构图，包含前端、后端和向量库之间的连接。"
                "\n\n系统架构图 OCR\n\nimage:ocr-region-1"
            ]
        ]
        assert bm25_index_client.documents[0].content == embedding_client.requests[0][0]
        payload = cast(dict[str, Any], vector_index_client.points[0]["payload"])
        assert payload["description"] == chunk.description
        assert payload["asset_paths"] == ["images/architecture.png"]
        assert payload["modality"] == "image"
        assert parse_job.logs is not None
        assert parse_job.logs["image_description"]["generated_count"] == 1

        chunks_response = client.get(
            f"/api/v1/files/{file_id}/chunks",
            headers=_headers(admin_token),
        )
        chunk_body = chunks_response.json()["items"][0]
        assert chunk_body["description"] == chunk.description
        assert chunk_body["modality"] == "image"
        assert chunk_body["asset_paths"] == ["images/architecture.png"]
        assert chunk_body["document_block_types"] == ["image_ocr"]
        assert chunk_body["image_url"].endswith("path=images%2Farchitecture.png")
        assert chunk_body["image_urls"] == [chunk_body["image_url"]]
        assert chunk_body["image_alt"] == chunk.description
        assert chunk_body["metadata"]["description_status"] == "generated"
    finally:
        app.dependency_overrides.clear()


def test_image_description_failure_continues_indexing_with_warning() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(
        result_state="done",
        result_zip=build_image_asset_mineru_zip(),
    )
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient()
    bm25_index_client = FakeBM25IndexClient()
    image_description_client = FakeImageDescriptionClient(fail=True)
    _install_overrides(
        session_factory,
        storage,
        mineru_client,
        embedding_client,
        vector_index_client,
        bm25_index_client,
        image_description_client,
    )
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")

        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("architecture.pdf", b"parse me", "application/pdf"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]
        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )

        assert status_response.status_code == 200
        assert status_response.json()["file_status"] == "indexed"
        with session_factory() as db:
            chunk = db.scalar(select(ChunkMetadata).where(ChunkMetadata.file_id == UUID(file_id)))
            parse_job = db.get(ParseJob, UUID(status_response.json()["latest_parse_job"]["id"]))
        assert chunk is not None
        assert parse_job is not None
        assert chunk.description is None
        assert chunk.chunk_metadata is not None
        assert chunk.chunk_metadata["description_status"] == "failed"
        assert chunk.chunk_metadata["description_error"] == "vision unavailable"
        assert embedding_client.requests == [["系统架构图 OCR\n\nimage:ocr-region-1"]]
        assert parse_job.logs is not None
        assert parse_job.logs["image_description"]["failed_count"] == 1
        assert parse_job.logs["image_description"]["warnings"][0]["message"] == (
            "vision unavailable"
        )
    finally:
        app.dependency_overrides.clear()


def test_delete_indexed_file_deactivates_chunks_and_qdrant_points() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(result_state="done")
    embedding_client = FakeEmbeddingClient()
    vector_index_client = FakeVectorIndexClient()
    bm25_index_client = FakeBM25IndexClient()
    _install_overrides(
        session_factory,
        storage,
        mineru_client,
        embedding_client,
        vector_index_client,
        bm25_index_client,
    )
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("report.txt", b"parse me", "text/plain"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]
        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )
        assert status_response.status_code == 200
        assert status_response.json()["file_status"] == "indexed"

        with session_factory() as db:
            active_chunk_ids = [
                str(chunk_id)
                for chunk_id in db.scalars(
                    select(ChunkMetadata.id).where(
                        ChunkMetadata.file_id == UUID(file_id),
                        ChunkMetadata.is_active.is_(True),
                    )
                ).all()
            ]
        assert len(active_chunk_ids) == 2

        delete_response = client.delete(
            f"/api/v1/files/{file_id}",
            headers=_headers(admin_token),
        )
        assert delete_response.status_code == 204

        with session_factory() as db:
            deleted_file = db.get(File, UUID(file_id))
            chunks = db.scalars(
                select(ChunkMetadata).where(ChunkMetadata.file_id == UUID(file_id))
            ).all()
            delete_audit = db.scalar(
                select(AuditLog).where(
                    AuditLog.action == "delete_file",
                    AuditLog.resource_id == UUID(file_id),
                )
            )

        assert deleted_file is not None
        assert deleted_file.status == "deleted"
        assert deleted_file.deleted_at is not None
        assert chunks
        assert all(chunk.is_active is False for chunk in chunks)
        assert sorted(vector_index_client.deactivated_point_ids) == sorted(active_chunk_ids)
        assert sorted(bm25_index_client.deactivated_chunk_ids) == sorted(active_chunk_ids)
        for point in vector_index_client.points:
            payload = cast(dict[str, Any], point["payload"])
            assert payload["is_active"] is False
        assert delete_audit is not None
        delete_details = cast(dict[str, Any], delete_audit.details)
        assert delete_details["inactive_chunk_count"] == 2
        assert delete_details["qdrant_points_deactivated"] == 2
        assert delete_details["qdrant_collection"] == "chunks"
        assert delete_details["bm25_documents_deactivated"] == 2
        assert delete_details["bm25_provider"] == "fake-bm25"
        assert delete_details["bm25_index"] == "chunks_bm25"
    finally:
        app.dependency_overrides.clear()


def test_retry_parse_marks_parse_job_failed_when_mineru_result_fails() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(result_state="failed")
    _install_overrides(session_factory, storage, mineru_client)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("bad.txt", b"parse me", "text/plain"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]

        retry_response = client.post(
            f"/api/v1/files/{file_id}/retry-parse",
            headers=_headers(admin_token),
        )
        assert retry_response.status_code == 202
        parse_job_id = retry_response.json()["id"]

        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )
        assert status_response.status_code == 200
        assert status_response.json()["file_status"] == "failed"
        assert status_response.json()["latest_parse_job"]["status"] == "failed"

        with session_factory() as db:
            parse_job = db.get(ParseJob, UUID(parse_job_id))
        assert parse_job is not None
        assert parse_job.error_code == "MINERU_PARSE_FAILED"
        assert parse_job.error_message == "MinerU parse failed."
        assert parse_job.finished_at is not None
        assert parse_job.logs is not None
        assert parse_job.logs["mineru_latest_state"] == "failed"
        assert parse_job.logs["mineru_error"]["code"] == "MINERU_PARSE_FAILED"
    finally:
        app.dependency_overrides.clear()


def test_retry_parse_records_mineru_submit_error_message() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(submit_error_message="MinerU API token is not configured.")
    _install_overrides(session_factory, storage, mineru_client)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("submit-error.txt", b"parse me", "text/plain"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]

        retry_response = client.post(
            f"/api/v1/files/{file_id}/retry-parse",
            headers=_headers(admin_token),
        )
        assert retry_response.status_code == 202
        assert retry_response.json()["status"] == "queued"

        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["file_status"] == "failed"
        assert status_body["latest_parse_job"]["status"] == "failed"
        assert status_body["latest_parse_job"]["error_code"] == "MINERU_SUBMIT_FAILED"
        assert (
            status_body["latest_parse_job"]["error_message"]
            == "MinerU API token is not configured."
        )
        assert status_body["latest_parse_job"]["logs"]["mineru_submit_error"] == {
            "message": "MinerU API token is not configured."
        }
    finally:
        app.dependency_overrides.clear()


def test_retry_parse_keeps_parsing_when_mineru_result_is_pending() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(result_state="running")
    _install_overrides(session_factory, storage, mineru_client)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("pending.txt", b"parse me", "text/plain"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]

        retry_response = client.post(
            f"/api/v1/files/{file_id}/retry-parse",
            headers=_headers(admin_token),
        )
        assert retry_response.status_code == 202

        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["file_status"] == "processing"
        assert status_body["latest_parse_job"]["status"] == "parsing"
        assert status_body["latest_parse_job"]["progress"] == 10
        assert status_body["latest_parse_job"]["logs"]["mineru_latest_state"] == "running"

        with session_factory() as db:
            parse_job = db.get(ParseJob, UUID(retry_response.json()["id"]))
        assert parse_job is not None
        assert parse_job.status == "parsing"
        assert parse_job.logs is not None
        assert parse_job.logs["mineru_latest_state"] == "running"
        assert not any(bucket == "parsed-results" for bucket, _key in storage.objects)
    finally:
        app.dependency_overrides.clear()


def test_retry_parse_fails_when_mineru_success_has_no_full_zip_url() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    mineru_client = FakeMineruClient(result_state="done", full_zip_url=None)
    _install_overrides(session_factory, storage, mineru_client)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_response = client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload",
            headers=_headers(admin_token),
            files=[("files", ("missing-result.txt", b"parse me", "text/plain"))],
        )
        file_id = upload_response.json()["uploaded"][0]["file"]["id"]

        retry_response = client.post(
            f"/api/v1/files/{file_id}/retry-parse",
            headers=_headers(admin_token),
        )
        assert retry_response.status_code == 202

        status_response = client.get(
            f"/api/v1/files/{file_id}/status",
            headers=_headers(admin_token),
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["file_status"] == "failed"
        assert status_body["latest_parse_job"]["status"] == "failed"
        assert status_body["latest_parse_job"]["error_code"] == "MINERU_RESULT_MISSING"
        assert "full_zip_url" in status_body["latest_parse_job"]["error_message"]
        assert status_body["latest_parse_job"]["logs"]["mineru_error"]["code"] == (
            "MINERU_RESULT_MISSING"
        )
    finally:
        app.dependency_overrides.clear()


def test_upload_rejects_inactive_knowledge_base_and_too_many_files() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_admin_user_and_kb(session_factory)
    storage = FakeObjectStorage()
    _install_overrides(session_factory, storage)
    settings = get_settings()
    original_max_batch_upload_count = settings.max_batch_upload_count
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        upload_url = f"/api/v1/knowledge-bases/{knowledge_base_id}/files/upload"

        settings.max_batch_upload_count = 1
        too_many = client.post(
            upload_url,
            headers=_headers(admin_token),
            files=[
                ("files", ("a.txt", b"a", "text/plain")),
                ("files", ("b.txt", b"b", "text/plain")),
            ],
        )
        assert too_many.status_code == 400
        assert too_many.json()["error"]["code"] == "TOO_MANY_FILES"
        settings.max_batch_upload_count = original_max_batch_upload_count

        with session_factory() as db:
            knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
            assert knowledge_base is not None
            knowledge_base.status = KnowledgeBaseStatus.DELETING.value
            db.commit()

        inactive = client.post(
            upload_url,
            headers=_headers(admin_token),
            files=[("files", ("inactive.txt", b"x", "text/plain"))],
        )
        assert inactive.status_code == 409
        assert inactive.json()["error"]["code"] == "KNOWLEDGE_BASE_INACTIVE"
    finally:
        settings.max_batch_upload_count = original_max_batch_upload_count
        app.dependency_overrides.clear()
