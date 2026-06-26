import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
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
from app.services.embedding import LocalDemoEmbeddingClient
from app.services.indexing import build_qdrant_point, write_chunk_tsv
from app.services.object_storage import ObjectStorage, get_object_storage
from app.services.vector_index import VectorIndexClientProtocol, get_vector_index_client

DEMO_KB_NAME = "Demo Fixture 知识库"
DEMO_FILE_NAME = "demo-rag-fixture.txt"
DEMO_USER_USERNAME = "demo_user"
DEMO_USER_PASSWORD = "DemoUserPassword123"

DEMO_CHUNKS = [
    {
        "content": (
            "井下落鱼可视化工具 使用步骤：第一步连接摄像探头，第二步下入井筒观察落鱼位置，"
            "第三步记录图像并输出处置建议。"
        ),
        "source_locator": "demo:section-1",
        "heading_path": ["井下落鱼可视化工具", "使用步骤"],
    },
    {
        "content": (
            "封隔器通用技术条件 关键要求：密封性能、耐压性能、坐封可靠性、解封可靠性" "和材料检验。"
        ),
        "source_locator": "demo:section-2",
        "heading_path": ["封隔器通用技术条件", "关键要求"],
    },
    {
        "content": "大修工艺技术 介绍了打捞、磨铣、套管修复、堵水和试压等工艺。",
        "source_locator": "demo:section-3",
        "heading_path": ["大修工艺技术", "工艺概览"],
    },
]


@dataclass(frozen=True)
class DemoFixtureResult:
    knowledge_base_id: str
    file_id: str
    parse_job_id: str
    chunk_ids: list[str]
    demo_user_username: str
    demo_user_password: str
    demo_question: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "knowledge_base_id": self.knowledge_base_id,
            "file_id": self.file_id,
            "parse_job_id": self.parse_job_id,
            "chunk_ids": self.chunk_ids,
            "demo_user_username": self.demo_user_username,
            "demo_user_password": self.demo_user_password,
            "demo_question": self.demo_question,
        }


def seed_demo_fixture(
    db: Session,
    *,
    vector_index_client: VectorIndexClientProtocol,
    storage: ObjectStorage | None = None,
) -> DemoFixtureResult:
    settings = get_settings()
    admin = create_default_admin(db)
    if admin is None:
        admin = db.scalar(select(User).where(User.username == settings.default_admin_username))
    if admin is None:
        raise RuntimeError("Default admin user could not be initialized.")

    demo_user = ensure_demo_user(db)
    knowledge_base = ensure_demo_knowledge_base(db, admin=admin)
    file = ensure_demo_file(db, knowledge_base=knowledge_base, admin=admin, storage=storage)

    active_chunk_ids = [
        str(chunk_id)
        for chunk_id in db.scalars(
            select(ChunkMetadata.id).where(
                ChunkMetadata.file_id == file.id,
                ChunkMetadata.is_active.is_(True),
            )
        ).all()
    ]
    vector_index_client.deactivate_points(point_ids=active_chunk_ids)
    for chunk in db.scalars(
        select(ChunkMetadata).where(
            ChunkMetadata.file_id == file.id,
            ChunkMetadata.is_active.is_(True),
        )
    ):
        chunk.is_active = False

    parse_job = ParseJob(
        file_id=file.id,
        knowledge_base_id=knowledge_base.id,
        status=ParseJobStatus.INDEXED.value,
        progress=100,
        logs={
            "provider": "demo_fixture",
            "mode": "local_seed",
            "warning": "Development/demo fixture; not a real MinerU/embedding/LLM result.",
        },
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        created_by=admin.id,
    )
    db.add(parse_job)
    db.flush()

    chunks = [
        ChunkMetadata(
            knowledge_base_id=knowledge_base.id,
            file_id=file.id,
            parse_job_id=parse_job.id,
            chunk_index=index,
            content=cast(str, item["content"]),
            content_hash=hash_text(cast(str, item["content"])),
            token_count=len(cast(str, item["content"]).split()),
            source_type="txt",
            source_locator=cast(str, item["source_locator"]),
            heading_path=cast(list[str], item["heading_path"]),
            chunk_metadata={"source": "demo_fixture"},
            is_active=True,
        )
        for index, item in enumerate(DEMO_CHUNKS)
    ]
    db.add_all(chunks)
    db.flush()
    for chunk in chunks:
        write_chunk_tsv(db, chunk=chunk)

    embedding_client = LocalDemoEmbeddingClient()
    vectors = embedding_client.embed_texts([chunk.content for chunk in chunks])
    vector_index_client.ensure_collection(vector_size=len(vectors[0]))
    vector_index_client.upsert_points(
        points=[
            build_qdrant_point(file=file, parse_job=parse_job, chunk=chunk, vector=vector)
            for chunk, vector in zip(chunks, vectors, strict=True)
        ]
    )

    file.status = FileStatus.INDEXED.value
    file.latest_parse_job_id = parse_job.id
    file.deleted_at = None
    db.commit()

    return DemoFixtureResult(
        knowledge_base_id=str(knowledge_base.id),
        file_id=str(file.id),
        parse_job_id=str(parse_job.id),
        chunk_ids=[str(chunk.id) for chunk in chunks],
        demo_user_username=demo_user.username,
        demo_user_password=DEMO_USER_PASSWORD,
        demo_question="井下落鱼可视化工具 使用步骤是什么？",
    )


def ensure_demo_user(db: Session) -> User:
    user = db.scalar(select(User).where(User.username == DEMO_USER_USERNAME))
    if user is None:
        user = User(
            email="demo-user@example.local",
            username=DEMO_USER_USERNAME,
            password_hash=hash_password(DEMO_USER_PASSWORD),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        user.profile = UserProfile(display_name="Demo User")
        db.add(user)
        db.flush()
        return user

    user.status = UserStatus.ACTIVE.value
    user.password_hash = hash_password(DEMO_USER_PASSWORD)
    if user.profile is None:
        user.profile = UserProfile(display_name="Demo User")
    else:
        user.profile.display_name = "Demo User"
    db.flush()
    return user


def ensure_demo_knowledge_base(db: Session, *, admin: User) -> KnowledgeBase:
    knowledge_base = db.scalar(select(KnowledgeBase).where(KnowledgeBase.name == DEMO_KB_NAME))
    if knowledge_base is None:
        knowledge_base = KnowledgeBase(
            name=DEMO_KB_NAME,
            description="Development-only fixture knowledge base for the first-version Demo.",
            status=KnowledgeBaseStatus.ACTIVE.value,
            settings={"source": "demo_fixture"},
            created_by=admin.id,
        )
        db.add(knowledge_base)
    else:
        knowledge_base.status = KnowledgeBaseStatus.ACTIVE.value
        knowledge_base.deleted_at = None
        knowledge_base.description = (
            "Development-only fixture knowledge base for the first-version Demo."
        )
        knowledge_base.settings = {"source": "demo_fixture"}
    db.flush()
    return knowledge_base


def ensure_demo_file(
    db: Session,
    *,
    knowledge_base: KnowledgeBase,
    admin: User,
    storage: ObjectStorage | None,
) -> File:
    content = build_fixture_file_content()
    file_hash = hash_text(content)
    storage_key = f"demo-fixtures/{knowledge_base.id}/{DEMO_FILE_NAME}"
    file = db.scalar(
        select(File).where(
            File.knowledge_base_id == knowledge_base.id,
            File.file_name == DEMO_FILE_NAME,
        )
    )
    if file is None:
        file = File(
            knowledge_base_id=knowledge_base.id,
            file_name=DEMO_FILE_NAME,
            file_ext=".txt",
            mime_type="text/plain",
            file_size=len(content.encode("utf-8")),
            file_hash=file_hash,
            storage_bucket=get_settings().raw_files_bucket,
            storage_key=storage_key,
            status=FileStatus.INDEXED.value,
            created_by=admin.id,
        )
        db.add(file)
    else:
        file.file_ext = ".txt"
        file.mime_type = "text/plain"
        file.file_size = len(content.encode("utf-8"))
        file.file_hash = file_hash
        file.storage_bucket = get_settings().raw_files_bucket
        file.storage_key = storage_key
        file.status = FileStatus.INDEXED.value
        file.deleted_at = None
    db.flush()
    if storage is not None:
        storage.put_object(
            bucket=get_settings().raw_files_bucket,
            key=storage_key,
            data=content.encode("utf-8"),
            content_type="text/plain",
            metadata={
                "file_id": str(file.id),
                "knowledge_base_id": str(knowledge_base.id),
                "file_hash": file_hash,
                "source": "demo_fixture",
            },
        )
    return file


def build_fixture_file_content() -> str:
    return "\n\n".join(str(item["content"]) for item in DEMO_CHUNKS)


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    settings = get_settings()
    if not settings.demo_fixture_enabled:
        raise SystemExit(
            "DEMO_FIXTURE_ENABLED must be true before seeding the development demo fixture."
        )
    with SessionLocal() as db:
        result = seed_demo_fixture(
            db,
            vector_index_client=get_vector_index_client(),
            storage=get_object_storage(),
        )
    print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
