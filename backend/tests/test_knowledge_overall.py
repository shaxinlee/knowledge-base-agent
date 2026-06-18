from typing import TypedDict
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
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
from app.services.knowledge_overall import (
    is_knowledge_overall_query,
    rebuild_knowledge_base_overall,
)


class StoredObject(TypedDict):
    data: bytes
    content_type: str | None
    metadata: dict[str, str]


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], StoredObject] = {}

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
        return self.objects[(bucket, key)]["data"]


def _make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _seed_chunked_knowledge_base(session_factory: sessionmaker[Session]) -> UUID:
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
            name="Overall KB",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={},
            created_by=admin.id,
        )
        db.add_all([reader, knowledge_base])
        db.flush()
        file = File(
            knowledge_base_id=knowledge_base.id,
            file_name="manual.pdf",
            file_ext=".pdf",
            mime_type="application/pdf",
            file_size=128,
            file_hash="a" * 64,
            storage_bucket="raw-files",
            storage_key="manual.pdf",
            status=FileStatus.PROCESSING.value,
            created_by=admin.id,
        )
        db.add(file)
        db.flush()
        parse_job = ParseJob(
            file_id=file.id,
            knowledge_base_id=knowledge_base.id,
            status=ParseJobStatus.EMBEDDING.value,
            progress=70,
            created_by=admin.id,
        )
        db.add(parse_job)
        db.flush()
        file.latest_parse_job_id = parse_job.id
        db.add(
            ChunkMetadata(
                knowledge_base_id=knowledge_base.id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                chunk_index=0,
                content="井下落鱼可视化工具用于井筒作业中的落鱼定位和可视化辅助判断。",
                content_hash="b" * 64,
                token_count=20,
                heading_path=["第一章", "工具介绍"],
                source_type="pdf",
                source_locator="pdf:p1",
                is_active=True,
                tsv="井下落鱼可视化工具",
            )
        )
        db.commit()
        return knowledge_base.id


def test_rebuild_knowledge_base_overall_writes_file_table() -> None:
    session_factory = _make_session_factory()
    knowledge_base_id = _seed_chunked_knowledge_base(session_factory)
    storage = FakeObjectStorage()

    with session_factory() as db:
        content = rebuild_knowledge_base_overall(
            db,
            knowledge_base_id=knowledge_base_id,
            storage=storage,
        )
        knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
        assert knowledge_base is not None
        assert knowledge_base.settings is not None
        overall = knowledge_base.settings["overall"]

    assert "Overall KB 知识库概览" in content
    assert "知识库创建时间 " in content
    assert "文件数量 1" in content
    assert "知识库包含的文件：" in content
    assert "| 序号 | 文件名称 | 文件添加时间 |" in content
    assert "manual.pdf" in content
    assert "| 1 |" in content
    assert "| 1 | manual.pdf |" in content
    assert content.count("manual.pdf") == 1
    assert "大概描述" not in content
    assert "井下落鱼可视化工具" not in content
    assert overall["bucket"] == "normalized-docs"
    assert overall["key"] == f"knowledge-bases/{knowledge_base_id}/overall.md"
    stored = storage.objects[("normalized-docs", overall["key"])]
    assert stored["content_type"] == "text/markdown; charset=utf-8"
    assert b"manual.pdf" in stored["data"]


def test_is_knowledge_overall_query_matches_catalog_questions() -> None:
    assert is_knowledge_overall_query("当前知识库都包含什么数据？")
    assert is_knowledge_overall_query("这个知识库有哪些文件")
    assert not is_knowledge_overall_query("RTTS封隔器如何解卡？")
