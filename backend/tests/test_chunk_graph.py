from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base
from app.models import (
    ChunkKnowledgeExtraction,
    ChunkMetadata,
    ChunkRelation,
    ChunkSummaryEmbedding,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseStatus,
    ParseJob,
    ParseJobStatus,
    User,
    UserRole,
    UserStatus,
)
from app.services.chunk_graph import (
    ChunkGraphItem,
    ChunkRelationDraft,
    build_chunk_graph_for_knowledge_base,
    calculate_chunk_relation_drafts,
    cosine_similarity,
    ensure_chunk_summary_embeddings,
    load_chunk_embedding_cache,
    load_chunk_graph_items,
    replace_chunk_relations,
)


class FakeEmbeddingClient:
    model = "fake-chunk-embedding"

    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self._vectors = vectors or {}
        self.calls: list[list[str]] = []

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        return [self._vectors.get(text, [0.0, 0.0]) for text in texts]


def make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def seed_chunks(
    session_factory: sessionmaker[Session],
) -> dict[str, object]:
    result: dict[str, object] = {}
    with session_factory() as db:
        user = User(
            email="chunk-graph@example.local",
            username="chunk-graph-admin",
            password_hash="hash",
            role=UserRole.ADMIN.value,
            status=UserStatus.ACTIVE.value,
        )
        db.add(user)
        db.flush()

        kb_a = KnowledgeBase(name="KB-A", status="active", created_by=user.id)
        kb_b = KnowledgeBase(name="KB-B", status="active", created_by=user.id)
        db.add_all([kb_a, kb_b])
        db.flush()
        result["kb_a_id"] = kb_a.id
        result["kb_b_id"] = kb_b.id

        file_a = File(
            file_name="doc_a.pdf",
            file_ext=".pdf",
            file_size=100,
            file_hash="aaaa",
            storage_bucket="raw-files",
            storage_key="doc_a.pdf",
            knowledge_base_id=kb_a.id,
            status=FileStatus.INDEXED.value,
            created_by=user.id,
        )
        file_b = File(
            file_name="doc_b.pdf",
            file_ext=".pdf",
            file_size=100,
            file_hash="bbbb",
            storage_bucket="raw-files",
            storage_key="doc_b.pdf",
            knowledge_base_id=kb_b.id,
            status=FileStatus.INDEXED.value,
            created_by=user.id,
        )
        db.add_all([file_a, file_b])
        db.flush()
        result["file_a_id"] = file_a.id
        result["file_b_id"] = file_b.id

        pja = ParseJob(
            file_id=file_a.id,
            knowledge_base_id=kb_a.id,
            status=ParseJobStatus.INDEXED.value,
            progress=100,
            created_by=user.id,
        )
        pjb = ParseJob(
            file_id=file_b.id,
            knowledge_base_id=kb_b.id,
            status=ParseJobStatus.INDEXED.value,
            progress=100,
            created_by=user.id,
        )
        db.add_all([pja, pjb])
        db.flush()
        file_a.parse_job_id = pja.id
        file_a.latest_parse_job_id = pja.id
        file_b.parse_job_id = pjb.id
        file_b.latest_parse_job_id = pjb.id

        chunks = {}
        for idx, (label, kb_id, file_id, pj_id) in enumerate([
            ("c1", kb_a.id, file_a.id, pja.id),
            ("c2", kb_a.id, file_a.id, pja.id),
            ("c3", kb_a.id, file_a.id, pja.id),
            ("c4", kb_b.id, file_b.id, pjb.id),
        ]):
            chunk = ChunkMetadata(
                knowledge_base_id=kb_id,
                file_id=file_id,
                parse_job_id=pj_id,
                chunk_index=idx,
                content=f"content-{label}",
                content_hash=f"hash-{label}",
                source_type="txt",
                source_locator=f"block-{idx}",
                is_active=True,
            )
            db.add(chunk)
            db.flush()
            chunks[label] = chunk.id
            result[f"{label}_id"] = chunk.id

        for label, summary_text in [
            ("c1", "数据库设计规范"),
            ("c2", "数据库索引优化"),
            ("c3", "前端组件库"),
            ("c4", "数据库备份方案"),
        ]:
            extraction = ChunkKnowledgeExtraction(
                chunk_id=chunks[label],
                file_id=result["file_a_id"] if label != "c4" else result["file_b_id"],
                parse_job_id=pja.id if label != "c4" else pjb.id,
                status="completed",
                short_summary=summary_text,
                prompt_version="chunk-knowledge-extraction-v1",
                extraction={"summary": summary_text},
            )
            db.add(extraction)

        db.commit()
    return result


def test_cosine_similarity_identical() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_empty() -> None:
    assert cosine_similarity([], []) == 0.0


def test_load_chunk_graph_items_filters_completed(
    session_factory=None,
) -> None:
    sf = session_factory or make_session_factory()
    seed_chunks(sf)
    with sf() as db:
        items = load_chunk_graph_items(db)
    assert len(items) == 4
    summaries = {item.short_summary for item in items}
    assert "数据库设计规范" in summaries


def test_load_chunk_graph_items_filters_by_kb() -> None:
    sf = make_session_factory()
    ids = seed_chunks(sf)
    with sf() as db:
        items = load_chunk_graph_items(db, knowledge_base_id=ids["kb_a_id"])
    assert len(items) == 3
    for item in items:
        assert item.knowledge_base_id == ids["kb_a_id"]


def test_ensure_chunk_summary_embeddings_caches() -> None:
    sf = make_session_factory()
    seed_chunks(sf)
    client = FakeEmbeddingClient(
        vectors={
            "数据库设计规范": [1.0, 0.0],
            "数据库索引优化": [0.9, 0.1],
            "前端组件库": [0.0, 1.0],
            "数据库备份方案": [0.8, 0.2],
        }
    )
    with sf() as db:
        items = load_chunk_graph_items(db)
    ensure_chunk_summary_embeddings(sf, items=items, embedding_client=client, batch_size=4)
    assert len(client.calls) == 1

    client2 = FakeEmbeddingClient(
        vectors={
            "数据库设计规范": [1.0, 0.0],
            "数据库索引优化": [0.9, 0.1],
            "前端组件库": [0.0, 1.0],
            "数据库备份方案": [0.8, 0.2],
        }
    )
    ensure_chunk_summary_embeddings(sf, items=items, embedding_client=client2, batch_size=4)
    assert len(client2.calls) == 0


def test_calculate_chunk_relation_drafts_threshold() -> None:
    items = [
        ChunkGraphItem(
            chunk_id=uuid4(),
            file_id=uuid4(),
            parse_job_id=uuid4(),
            knowledge_base_id=uuid4(),
            short_summary="a",
            summary_hash="a",
        ),
        ChunkGraphItem(
            chunk_id=uuid4(),
            file_id=uuid4(),
            parse_job_id=uuid4(),
            knowledge_base_id=uuid4(),
            short_summary="b",
            summary_hash="b",
        ),
    ]
    vectors = {
        items[0].chunk_id: [1.0, 0.0],
        items[1].chunk_id: [0.0, 1.0],
    }
    drafts = calculate_chunk_relation_drafts(
        items, vectors, threshold=0.5, max_relations_per_chunk=4
    )
    assert len(drafts) == 0


def test_calculate_chunk_relation_drafts_same_kb() -> None:
    kb_id = uuid4()
    file_id = uuid4()
    pj_id = uuid4()
    items = [
        ChunkGraphItem(
            chunk_id=uuid4(),
            file_id=file_id,
            parse_job_id=pj_id,
            knowledge_base_id=kb_id,
            short_summary="a",
            summary_hash="a",
        ),
        ChunkGraphItem(
            chunk_id=uuid4(),
            file_id=file_id,
            parse_job_id=pj_id,
            knowledge_base_id=kb_id,
            short_summary="b",
            summary_hash="b",
        ),
    ]
    vectors = {
        items[0].chunk_id: [1.0, 0.0],
        items[1].chunk_id: [0.9, 0.1],
    }
    drafts = calculate_chunk_relation_drafts(
        items, vectors, threshold=0.5, max_relations_per_chunk=4
    )
    assert len(drafts) == 1
    assert drafts[0].similarity > 0.9
    assert drafts[0].knowledge_base_id == kb_id


def test_calculate_chunk_relation_drafts_cross_kb_excluded() -> None:
    kb_a = uuid4()
    kb_b = uuid4()
    file_id = uuid4()
    pj_id = uuid4()
    items = [
        ChunkGraphItem(
            chunk_id=uuid4(),
            file_id=file_id,
            parse_job_id=pj_id,
            knowledge_base_id=kb_a,
            short_summary="a",
            summary_hash="a",
        ),
        ChunkGraphItem(
            chunk_id=uuid4(),
            file_id=file_id,
            parse_job_id=pj_id,
            knowledge_base_id=kb_b,
            short_summary="b",
            summary_hash="b",
        ),
    ]
    vectors = {
        items[0].chunk_id: [1.0, 0.0],
        items[1].chunk_id: [0.9, 0.1],
    }
    drafts = calculate_chunk_relation_drafts(
        items, vectors, threshold=0.5, max_relations_per_chunk=4
    )
    assert len(drafts) == 0


def test_calculate_chunk_relation_drafts_top_k() -> None:
    kb_id = uuid4()
    file_id = uuid4()
    pj_id = uuid4()
    items = []
    for i in range(6):
        items.append(
            ChunkGraphItem(
                chunk_id=uuid4(),
                file_id=file_id,
                parse_job_id=pj_id,
                knowledge_base_id=kb_id,
                short_summary=f"item-{i}",
                summary_hash=f"hash-{i}",
            )
        )
    vectors = {
        items[0].chunk_id: [1.0, 0.0],
        items[1].chunk_id: [0.95, 0.05],
        items[2].chunk_id: [0.90, 0.10],
        items[3].chunk_id: [0.85, 0.15],
        items[4].chunk_id: [0.80, 0.20],
        items[5].chunk_id: [0.75, 0.25],
    }
    drafts = calculate_chunk_relation_drafts(
        items, vectors, threshold=0.5, max_relations_per_chunk=2
    )
    neighbors_of_first = [
        d for d in drafts
        if items[0].chunk_id in (d.source_chunk_id, d.target_chunk_id)
    ]
    assert len(neighbors_of_first) == 2


def test_replace_chunk_relations_per_kb() -> None:
    sf = make_session_factory()
    seed_chunks(sf)
    kb_a_id = None
    with sf() as db:
        kb_a_id = db.scalars(
            select(KnowledgeBase.id).where(KnowledgeBase.name == "KB-A")
        ).first()

    draft = ChunkRelationDraft(
        source_chunk_id=uuid4(),
        target_chunk_id=uuid4(),
        source_file_id=uuid4(),
        target_file_id=uuid4(),
        knowledge_base_id=kb_a_id,
        similarity=0.8,
    )

    with sf() as db:
        file_a = db.scalars(
            select(File).where(File.file_name == "doc_a.pdf")
        ).first()
        chunk = db.scalars(
            select(ChunkMetadata).where(ChunkMetadata.file_id == file_a.id)
        ).first()
        draft = ChunkRelationDraft(
            source_chunk_id=chunk.id,
            target_chunk_id=chunk.id,
            source_file_id=file_a.id,
            target_file_id=file_a.id,
            knowledge_base_id=kb_a_id,
            similarity=0.8,
        )

    replace_chunk_relations(
        sf,
        knowledge_base_id=kb_a_id,
        drafts=[draft],
        embedding_model="fake-model",
    )
    with sf() as db:
        relations = db.scalars(
            select(ChunkRelation).where(
                ChunkRelation.knowledge_base_id == kb_a_id
            )
        ).all()
    assert len(relations) == 1


def test_build_chunk_graph_full_pipeline() -> None:
    sf = make_session_factory()
    ids = seed_chunks(sf)
    client = FakeEmbeddingClient(
        vectors={
            "数据库设计规范": [1.0, 0.0],
            "数据库索引优化": [0.9, 0.1],
            "前端组件库": [0.0, 1.0],
        }
    )
    relations_count = build_chunk_graph_for_knowledge_base(
        sf,
        knowledge_base_id=ids["kb_a_id"],
        embedding_client=client,
        batch_size=4,
        threshold=0.5,
        max_relations_per_chunk=4,
    )
    assert relations_count >= 1
    with sf() as db:
        embeddings = db.scalars(
            select(ChunkSummaryEmbedding).where(
                ChunkSummaryEmbedding.knowledge_base_id == ids["kb_a_id"]
            )
        ).all()
        assert len(embeddings) == 3
        relations = db.scalars(
            select(ChunkRelation).where(
                ChunkRelation.knowledge_base_id == ids["kb_a_id"]
            )
        ).all()
        assert len(relations) == relations_count
        for rel in relations:
            assert rel.similarity >= 0.5
