import asyncio
import hashlib
import logging
import math
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings
from app.core.errors import ApiError
from app.models import (
    CommunitySummaryStatus,
    DocumentSummary,
    DocumentSummaryEmbedding,
    DocumentSummaryRelation,
    DocumentSummaryStatus,
    File,
    KnowledgeBase,
    KnowledgeBaseCommunitySummary,
    KnowledgeBaseStatus,
    KnowledgeGraphBuildStatus,
    KnowledgeGraphState,
)
from app.schemas.knowledge_graph import (
    CommunitySummaryResponse,
    KnowledgeGraphEdge,
    KnowledgeGraphNode,
    KnowledgeGraphResponse,
)
from app.services.document_summary_llm import (
    COMMUNITY_PROMPT_VERSION,
    DocumentSummaryLLMClient,
    DocumentSummaryLLMError,
    SummarySource,
    get_document_summary_llm_config,
)
from app.services.embedding import EmbeddingClientProtocol, get_embedding_client

logger = logging.getLogger(__name__)
GRAPH_STATE_KEY = "global"


@dataclass(frozen=True)
class GraphDocument:
    summary_id: UUID
    file_id: UUID
    parse_job_id: UUID
    knowledge_base_id: UUID
    file_name: str
    file_ext: str
    knowledge_base_name: str
    summary: str
    summary_status: str
    summary_hash: str


@dataclass(frozen=True)
class RelationDraft:
    source_summary_id: UUID
    target_summary_id: UUID
    source_file_id: UUID
    target_file_id: UUID
    source_knowledge_base_id: UUID
    target_knowledge_base_id: UUID
    similarity: float


@dataclass(frozen=True)
class SummaryCoverage:
    total: int = 0
    summarized: int = 0
    pending: int = 0
    failed: int = 0
    not_ready: int = 0


def load_graph_documents(db: Session) -> list[GraphDocument]:
    rows = db.execute(
        select(DocumentSummary, File, KnowledgeBase)
        .join(File, File.id == DocumentSummary.file_id)
        .join(KnowledgeBase, KnowledgeBase.id == DocumentSummary.knowledge_base_id)
        .where(
            DocumentSummary.status.in_(
                [
                    DocumentSummaryStatus.COMPLETED.value,
                    DocumentSummaryStatus.PARTIALLY_COMPLETED.value,
                ]
            ),
            DocumentSummary.summary.is_not(None),
            File.deleted_at.is_(None),
            File.latest_parse_job_id == DocumentSummary.parse_job_id,
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        )
        .order_by(KnowledgeBase.created_at.asc(), File.created_at.asc())
    ).all()
    return [
        GraphDocument(
            summary_id=summary.id,
            file_id=file.id,
            parse_job_id=summary.parse_job_id,
            knowledge_base_id=knowledge_base.id,
            file_name=file.file_name,
            file_ext=file.file_ext,
            knowledge_base_name=knowledge_base.name,
            summary=summary.summary or "",
            summary_status=summary.status,
            summary_hash=hashlib.sha256((summary.summary or "").encode("utf-8")).hexdigest(),
        )
        for summary, file, knowledge_base in rows
    ]


def load_summary_coverage(
    db: Session,
    *,
    knowledge_base_id: UUID | None,
) -> SummaryCoverage:
    query = (
        select(File, DocumentSummary.status, DocumentSummary.summary)
        .join(KnowledgeBase, KnowledgeBase.id == File.knowledge_base_id)
        .outerjoin(
            DocumentSummary,
            (DocumentSummary.file_id == File.id)
            & (DocumentSummary.parse_job_id == File.latest_parse_job_id),
        )
        .where(
            File.deleted_at.is_(None),
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        )
    )
    if knowledge_base_id is not None:
        query = query.where(File.knowledge_base_id == knowledge_base_id)

    total = summarized = pending = failed = not_ready = 0
    for file, status, summary in db.execute(query).all():
        total += 1
        if status in {
            DocumentSummaryStatus.COMPLETED.value,
            DocumentSummaryStatus.PARTIALLY_COMPLETED.value,
        } and summary:
            summarized += 1
        elif status in {
            DocumentSummaryStatus.PENDING.value,
            DocumentSummaryStatus.RUNNING.value,
        }:
            pending += 1
        elif status == DocumentSummaryStatus.FAILED.value:
            failed += 1
        else:
            not_ready += 1
    return SummaryCoverage(
        total=total,
        summarized=summarized,
        pending=pending,
        failed=failed,
        not_ready=not_ready,
    )


def build_graph_fingerprint(documents: list[GraphDocument]) -> str:
    raw = "\n".join(
        f"{document.summary_id}:{document.summary_hash}" for document in documents
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_create_graph_state(db: Session) -> KnowledgeGraphState:
    state = db.scalar(
        select(KnowledgeGraphState).where(KnowledgeGraphState.state_key == GRAPH_STATE_KEY)
    )
    if state is None:
        state = KnowledgeGraphState(
            state_key=GRAPH_STATE_KEY,
            status=KnowledgeGraphBuildStatus.PENDING.value,
        )
        db.add(state)
        db.flush()
    return state


def request_knowledge_graph_refresh(
    db: Session,
    *,
    force_embeddings: bool,
) -> KnowledgeGraphState:
    state = get_or_create_graph_state(db)
    state.status = KnowledgeGraphBuildStatus.PENDING.value
    state.source_fingerprint = None
    state.error_code = None
    state.error_message = None
    if force_embeddings:
        db.execute(delete(DocumentSummaryEmbedding))
    db.commit()
    db.refresh(state)
    return state


def prepare_graph_build(
    session_factory: sessionmaker[Session],
) -> tuple[list[GraphDocument], str] | None:
    with session_factory() as db:
        documents = load_graph_documents(db)
        fingerprint = build_graph_fingerprint(documents)
        state = get_or_create_graph_state(db)
        if (
            state.status == KnowledgeGraphBuildStatus.COMPLETED.value
            and state.source_fingerprint == fingerprint
            and not communities_need_update(db, documents)
        ):
            db.commit()
            return None
        state.status = KnowledgeGraphBuildStatus.RUNNING.value
        state.started_at = datetime.now(UTC)
        state.finished_at = None
        state.error_code = None
        state.error_message = None
        state.document_count = len(documents)
        db.commit()
        return documents, fingerprint


def communities_need_update(
    db: Session,
    documents: list[GraphDocument],
) -> bool:
    grouped: dict[UUID, list[GraphDocument]] = defaultdict(list)
    for document in documents:
        grouped[document.knowledge_base_id].append(document)
    rows = {
        row.knowledge_base_id: row
        for row in db.scalars(select(KnowledgeBaseCommunitySummary)).all()
    }
    knowledge_bases = list(
        db.scalars(
            select(KnowledgeBase).where(
                KnowledgeBase.deleted_at.is_(None),
                KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
            )
        ).all()
    )
    for knowledge_base in knowledge_bases:
        kb_documents = grouped.get(knowledge_base.id, [])
        fingerprint = build_community_fingerprint(kb_documents)
        row = rows.get(knowledge_base.id)
        expected_status = (
            CommunitySummaryStatus.COMPLETED.value
            if kb_documents
            else CommunitySummaryStatus.NOT_READY.value
        )
        if (
            row is None
            or row.status != expected_status
            or row.source_fingerprint != fingerprint
        ):
            return True
    return False


def load_embedding_cache(
    session_factory: sessionmaker[Session],
    *,
    summary_ids: list[UUID],
) -> dict[UUID, DocumentSummaryEmbedding]:
    if not summary_ids:
        return {}
    with session_factory() as db:
        return {
            row.document_summary_id: row
            for row in db.scalars(
                select(DocumentSummaryEmbedding).where(
                    DocumentSummaryEmbedding.document_summary_id.in_(summary_ids)
                )
            ).all()
        }


def save_embedding_batch(
    session_factory: sessionmaker[Session],
    *,
    documents: list[GraphDocument],
    vectors: list[list[float]],
    embedding_model: str,
) -> None:
    with session_factory() as db:
        existing = {
            row.document_summary_id: row
            for row in db.scalars(
                select(DocumentSummaryEmbedding).where(
                    DocumentSummaryEmbedding.document_summary_id.in_(
                        [document.summary_id for document in documents]
                    )
                )
            ).all()
        }
        for document, vector in zip(documents, vectors, strict=True):
            row = existing.get(document.summary_id)
            if row is None:
                row = DocumentSummaryEmbedding(
                    document_summary_id=document.summary_id,
                    knowledge_base_id=document.knowledge_base_id,
                    file_id=document.file_id,
                    parse_job_id=document.parse_job_id,
                    vector=vector,
                    vector_size=len(vector),
                    embedding_model=embedding_model,
                    summary_hash=document.summary_hash,
                )
                db.add(row)
            else:
                row.vector = vector
                row.vector_size = len(vector)
                row.embedding_model = embedding_model
                row.summary_hash = document.summary_hash
        db.commit()


def ensure_document_embeddings(
    session_factory: sessionmaker[Session],
    *,
    documents: list[GraphDocument],
    embedding_client: EmbeddingClientProtocol,
    batch_size: int,
) -> dict[UUID, list[float]]:
    cached = load_embedding_cache(
        session_factory,
        summary_ids=[document.summary_id for document in documents],
    )
    stale = [
        document
        for document in documents
        if (
            document.summary_id not in cached
            or cached[document.summary_id].summary_hash != document.summary_hash
            or cached[document.summary_id].embedding_model != embedding_client.model
        )
    ]
    for start in range(0, len(stale), batch_size):
        batch = stale[start : start + batch_size]
        vectors = embedding_client.embed_texts([document.summary for document in batch])
        if len(vectors) != len(batch):
            raise ApiError(
                code="EMBEDDING_VECTOR_COUNT_MISMATCH",
                message="Document summary embedding count does not match document count.",
                status_code=502,
                details={"expected": len(batch), "actual": len(vectors)},
            )
        save_embedding_batch(
            session_factory,
            documents=batch,
            vectors=vectors,
            embedding_model=embedding_client.model,
        )
    refreshed = load_embedding_cache(
        session_factory,
        summary_ids=[document.summary_id for document in documents],
    )
    return {
        summary_id: [float(value) for value in row.vector]
        for summary_id, row in refreshed.items()
    }


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_norm * right_norm)))


def calculate_relation_drafts(
    documents: list[GraphDocument],
    vectors: dict[UUID, list[float]],
    *,
    threshold: float,
    max_relations_per_document: int,
) -> list[RelationDraft]:
    ranked: dict[UUID, list[tuple[float, GraphDocument]]] = defaultdict(list)
    documents_by_id = {document.summary_id: document for document in documents}
    for index, left in enumerate(documents):
        left_vector = vectors.get(left.summary_id)
        if left_vector is None:
            continue
        for right in documents[index + 1 :]:
            right_vector = vectors.get(right.summary_id)
            if right_vector is None:
                continue
            similarity = cosine_similarity(left_vector, right_vector)
            if similarity < threshold:
                continue
            ranked[left.summary_id].append((similarity, right))
            ranked[right.summary_id].append((similarity, left))

    selected_pairs: dict[tuple[UUID, UUID], float] = {}
    for summary_id, candidates in ranked.items():
        for similarity, related in sorted(
            candidates,
            key=lambda item: (-item[0], item[1].file_name),
        )[:max_relations_per_document]:
            pair = tuple(sorted((summary_id, related.summary_id), key=str))
            selected_pairs[pair] = max(selected_pairs.get(pair, 0.0), similarity)

    drafts: list[RelationDraft] = []
    for (source_id, target_id), similarity in sorted(
        selected_pairs.items(),
        key=lambda item: (-item[1], str(item[0][0]), str(item[0][1])),
    ):
        source = documents_by_id[source_id]
        target = documents_by_id[target_id]
        drafts.append(
            RelationDraft(
                source_summary_id=source_id,
                target_summary_id=target_id,
                source_file_id=source.file_id,
                target_file_id=target.file_id,
                source_knowledge_base_id=source.knowledge_base_id,
                target_knowledge_base_id=target.knowledge_base_id,
                similarity=similarity,
            )
        )
    return drafts


def replace_relations(
    session_factory: sessionmaker[Session],
    *,
    drafts: list[RelationDraft],
    embedding_model: str,
) -> None:
    with session_factory() as db:
        db.execute(delete(DocumentSummaryRelation))
        db.add_all(
            [
                DocumentSummaryRelation(
                    source_document_summary_id=draft.source_summary_id,
                    target_document_summary_id=draft.target_summary_id,
                    source_file_id=draft.source_file_id,
                    target_file_id=draft.target_file_id,
                    source_knowledge_base_id=draft.source_knowledge_base_id,
                    target_knowledge_base_id=draft.target_knowledge_base_id,
                    similarity=draft.similarity,
                    cross_knowledge_base=(
                        draft.source_knowledge_base_id
                        != draft.target_knowledge_base_id
                    ),
                    embedding_model=embedding_model,
                )
                for draft in drafts
            ]
        )
        db.commit()


def build_community_fingerprint(documents: list[GraphDocument]) -> str:
    return hashlib.sha256(
        "\n".join(
            f"{document.summary_id}:{document.summary_hash}" for document in documents
        ).encode("utf-8")
    ).hexdigest()


def prepare_community_updates(
    session_factory: sessionmaker[Session],
    *,
    documents: list[GraphDocument],
) -> list[tuple[UUID, str, list[GraphDocument], str]]:
    grouped: dict[UUID, list[GraphDocument]] = defaultdict(list)
    for document in documents:
        grouped[document.knowledge_base_id].append(document)
    with session_factory() as db:
        knowledge_bases = list(
            db.scalars(
                select(KnowledgeBase).where(
                    KnowledgeBase.deleted_at.is_(None),
                    KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
                )
            ).all()
        )
        updates: list[tuple[UUID, str, list[GraphDocument], str]] = []
        for knowledge_base in knowledge_bases:
            kb_documents = grouped.get(knowledge_base.id, [])
            fingerprint = build_community_fingerprint(kb_documents)
            row = db.scalar(
                select(KnowledgeBaseCommunitySummary).where(
                    KnowledgeBaseCommunitySummary.knowledge_base_id
                    == knowledge_base.id
                )
            )
            if row is None:
                row = KnowledgeBaseCommunitySummary(
                    knowledge_base_id=knowledge_base.id,
                    status=CommunitySummaryStatus.PENDING.value,
                    prompt_version=COMMUNITY_PROMPT_VERSION,
                )
                db.add(row)
                db.flush()
            if not kb_documents:
                row.status = CommunitySummaryStatus.NOT_READY.value
                row.document_count = 0
                row.source_fingerprint = fingerprint
                row.error_code = None
                row.error_message = None
                continue
            if (
                row.status == CommunitySummaryStatus.COMPLETED.value
                and row.source_fingerprint == fingerprint
            ):
                continue
            row.status = CommunitySummaryStatus.RUNNING.value
            row.document_count = len(kb_documents)
            row.started_at = datetime.now(UTC)
            row.finished_at = None
            row.error_code = None
            row.error_message = None
            updates.append(
                (knowledge_base.id, knowledge_base.name, kb_documents, fingerprint)
            )
        db.commit()
        return updates


def save_community_success(
    session_factory: sessionmaker[Session],
    *,
    knowledge_base_id: UUID,
    fingerprint: str,
    summary_text: str,
    model_name: str,
    reduction_level: int,
) -> None:
    with session_factory() as db:
        row = db.scalar(
            select(KnowledgeBaseCommunitySummary).where(
                KnowledgeBaseCommunitySummary.knowledge_base_id == knowledge_base_id
            )
        )
        if row is None:
            return
        row.status = CommunitySummaryStatus.COMPLETED.value
        row.summary = summary_text
        row.source_fingerprint = fingerprint
        row.model_name = model_name
        row.prompt_version = COMMUNITY_PROMPT_VERSION
        row.reduction_level = reduction_level
        row.error_code = None
        row.error_message = None
        row.finished_at = datetime.now(UTC)
        db.commit()


def save_community_failure(
    session_factory: sessionmaker[Session],
    *,
    knowledge_base_id: UUID,
    fingerprint: str,
    error_code: str,
    error_message: str,
) -> None:
    with session_factory() as db:
        row = db.scalar(
            select(KnowledgeBaseCommunitySummary).where(
                KnowledgeBaseCommunitySummary.knowledge_base_id == knowledge_base_id
            )
        )
        if row is None:
            return
        row.status = CommunitySummaryStatus.FAILED.value
        row.source_fingerprint = fingerprint
        row.error_code = error_code
        row.error_message = error_message[:4000]
        row.finished_at = datetime.now(UTC)
        db.commit()


async def update_community_summaries(
    *,
    session_factory: sessionmaker[Session],
    documents: list[GraphDocument],
    llm_client: DocumentSummaryLLMClient,
    concurrency: int,
) -> dict[str, int]:
    updates = await asyncio.to_thread(
        prepare_community_updates,
        session_factory,
        documents=documents,
    )
    semaphore = asyncio.Semaphore(concurrency)
    succeeded = 0
    failed = 0

    async def update_one(
        knowledge_base_id: UUID,
        _knowledge_base_name: str,
        kb_documents: list[GraphDocument],
        fingerprint: str,
    ) -> bool:
        async with semaphore:
            sources = [
                SummarySource(
                    chunk_id=str(document.file_id),
                    section_path=document.file_name,
                    source_locator="",
                    short_summary=document.summary,
                )
                for document in kb_documents
            ]
            try:
                summary_text, reduction_level = await llm_client.summarize_community(
                    sources
                )
                await asyncio.to_thread(
                    save_community_success,
                    session_factory,
                    knowledge_base_id=knowledge_base_id,
                    fingerprint=fingerprint,
                    summary_text=summary_text,
                    model_name=llm_client.model,
                    reduction_level=reduction_level,
                )
                return True
            except DocumentSummaryLLMError as exc:
                await asyncio.to_thread(
                    save_community_failure,
                    session_factory,
                    knowledge_base_id=knowledge_base_id,
                    fingerprint=fingerprint,
                    error_code=exc.code,
                    error_message=str(exc),
                )
                return False
            except Exception as exc:
                logger.exception(
                    "Knowledge-base community summary failed knowledge_base_id=%s",
                    knowledge_base_id,
                )
                await asyncio.to_thread(
                    save_community_failure,
                    session_factory,
                    knowledge_base_id=knowledge_base_id,
                    fingerprint=fingerprint,
                    error_code="COMMUNITY_SUMMARY_FAILED",
                    error_message=str(exc),
                )
                return False

    results = await asyncio.gather(*(update_one(*update) for update in updates))
    succeeded += sum(1 for result in results if result)
    failed += sum(1 for result in results if not result)
    return {"updated": len(updates), "succeeded": succeeded, "failed": failed}


def finish_graph_build(
    session_factory: sessionmaker[Session],
    *,
    fingerprint: str,
    document_count: int,
    relation_count: int,
    embedding_model: str,
    metadata: dict[str, int],
) -> None:
    with session_factory() as db:
        state = get_or_create_graph_state(db)
        state.status = KnowledgeGraphBuildStatus.COMPLETED.value
        state.source_fingerprint = fingerprint
        state.document_count = document_count
        state.relation_count = relation_count
        state.embedding_model = embedding_model
        state.error_code = None
        state.error_message = None
        state.build_metadata = metadata
        state.finished_at = datetime.now(UTC)
        db.commit()


def fail_graph_build(
    session_factory: sessionmaker[Session],
    *,
    error_code: str,
    error_message: str,
) -> None:
    with session_factory() as db:
        state = get_or_create_graph_state(db)
        state.status = KnowledgeGraphBuildStatus.FAILED.value
        state.error_code = error_code
        state.error_message = error_message[:4000]
        state.finished_at = datetime.now(UTC)
        db.commit()


async def rebuild_knowledge_graph(
    *,
    session_factory: sessionmaker[Session],
    settings: Settings,
    embedding_client: EmbeddingClientProtocol,
    llm_client: DocumentSummaryLLMClient,
) -> bool:
    prepared = await asyncio.to_thread(prepare_graph_build, session_factory)
    if prepared is None:
        return False
    documents, fingerprint = prepared
    try:
        vectors = await asyncio.to_thread(
            ensure_document_embeddings,
            session_factory,
            documents=documents,
            embedding_client=embedding_client,
            batch_size=settings.knowledge_graph_embedding_batch_size,
        )
        drafts = await asyncio.to_thread(
            calculate_relation_drafts,
            documents,
            vectors,
            threshold=settings.knowledge_graph_similarity_threshold,
            max_relations_per_document=settings.knowledge_graph_max_relations_per_document,
        )
        await asyncio.to_thread(
            replace_relations,
            session_factory,
            drafts=drafts,
            embedding_model=embedding_client.model,
        )
        community_stats = await update_community_summaries(
            session_factory=session_factory,
            documents=documents,
            llm_client=llm_client,
            concurrency=settings.knowledge_graph_community_concurrency,
        )
        await asyncio.to_thread(
            finish_graph_build,
            session_factory,
            fingerprint=fingerprint,
            document_count=len(documents),
            relation_count=len(drafts),
            embedding_model=embedding_client.model,
            metadata=community_stats,
        )
        return True
    except Exception as exc:
        logger.exception("Knowledge graph rebuild failed.")
        await asyncio.to_thread(
            fail_graph_build,
            session_factory,
            error_code="KNOWLEDGE_GRAPH_BUILD_FAILED",
            error_message=str(exc),
        )
        return False


def get_knowledge_graph_response(
    db: Session,
    *,
    knowledge_base_id: UUID | None,
    include_cross_knowledge_base: bool,
    min_similarity: float,
    settings: Settings | None = None,
) -> KnowledgeGraphResponse:
    settings = settings or get_settings()
    state = get_or_create_graph_state(db)
    documents = load_graph_documents(db)
    coverage = load_summary_coverage(db, knowledge_base_id=knowledge_base_id)
    documents_by_summary_id = {
        document.summary_id: document for document in documents
    }
    relation_query = select(DocumentSummaryRelation).where(
        DocumentSummaryRelation.similarity >= min_similarity
    )
    if knowledge_base_id is not None:
        if include_cross_knowledge_base:
            relation_query = relation_query.where(
                or_(
                    DocumentSummaryRelation.source_knowledge_base_id
                    == knowledge_base_id,
                    DocumentSummaryRelation.target_knowledge_base_id
                    == knowledge_base_id,
                )
            )
        else:
            relation_query = relation_query.where(
                DocumentSummaryRelation.source_knowledge_base_id
                == knowledge_base_id,
                DocumentSummaryRelation.target_knowledge_base_id
                == knowledge_base_id,
            )
    relations = list(
        db.scalars(
            relation_query.order_by(DocumentSummaryRelation.similarity.desc())
        ).all()
    )
    selected_summary_ids: set[UUID]
    if knowledge_base_id is None:
        selected_summary_ids = set(documents_by_summary_id)
    else:
        selected_summary_ids = {
            document.summary_id
            for document in documents
            if document.knowledge_base_id == knowledge_base_id
        }
        if include_cross_knowledge_base:
            for relation in relations:
                selected_summary_ids.add(relation.source_document_summary_id)
                selected_summary_ids.add(relation.target_document_summary_id)
    relation_counts: dict[UUID, int] = defaultdict(int)
    edges: list[KnowledgeGraphEdge] = []
    for relation in relations:
        if (
            relation.source_document_summary_id not in selected_summary_ids
            or relation.target_document_summary_id not in selected_summary_ids
        ):
            continue
        relation_counts[relation.source_document_summary_id] += 1
        relation_counts[relation.target_document_summary_id] += 1
        edges.append(
            KnowledgeGraphEdge(
                id=str(relation.id),
                source=str(relation.source_document_summary_id),
                target=str(relation.target_document_summary_id),
                similarity=relation.similarity,
                cross_knowledge_base=relation.cross_knowledge_base,
            )
        )
    nodes = [
        KnowledgeGraphNode(
            id=str(document.summary_id),
            file_id=str(document.file_id),
            document_summary_id=str(document.summary_id),
            file_name=document.file_name,
            file_ext=document.file_ext,
            knowledge_base_id=str(document.knowledge_base_id),
            knowledge_base_name=document.knowledge_base_name,
            summary=document.summary,
            summary_status=document.summary_status,
            relation_count=relation_counts.get(document.summary_id, 0),
        )
        for document in documents
        if document.summary_id in selected_summary_ids
    ]
    community_query = (
        select(KnowledgeBaseCommunitySummary, KnowledgeBase)
        .join(
            KnowledgeBase,
            KnowledgeBase.id == KnowledgeBaseCommunitySummary.knowledge_base_id,
        )
        .where(
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        )
    )
    if knowledge_base_id is not None:
        relevant_kb_ids = {
            UUID(node.knowledge_base_id)
            for node in nodes
        } or {knowledge_base_id}
        community_query = community_query.where(
            KnowledgeBaseCommunitySummary.knowledge_base_id.in_(relevant_kb_ids)
        )
    communities = [
        build_community_response(row, knowledge_base)
        for row, knowledge_base in db.execute(
            community_query.order_by(KnowledgeBase.name.asc())
        ).all()
    ]
    db.commit()
    return KnowledgeGraphResponse(
        status=state.status,
        source_fingerprint=state.source_fingerprint,
        document_count=len(nodes),
        total_document_count=coverage.total,
        summarized_document_count=coverage.summarized,
        pending_summary_count=coverage.pending,
        failed_summary_count=coverage.failed,
        not_ready_document_count=coverage.not_ready,
        relation_count=len(edges),
        embedding_model=state.embedding_model,
        similarity_threshold=settings.knowledge_graph_similarity_threshold,
        max_relations_per_document=settings.knowledge_graph_max_relations_per_document,
        nodes=nodes,
        edges=edges,
        communities=communities,
        updated_at=state.updated_at,
    )


def get_community_summary_response(
    db: Session,
    *,
    knowledge_base_id: UUID,
) -> CommunitySummaryResponse:
    knowledge_base = db.scalar(
        select(KnowledgeBase).where(
            KnowledgeBase.id == knowledge_base_id,
            KnowledgeBase.deleted_at.is_(None),
            KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        )
    )
    if knowledge_base is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Knowledge base was not found.",
            status_code=404,
        )
    row = db.scalar(
        select(KnowledgeBaseCommunitySummary).where(
            KnowledgeBaseCommunitySummary.knowledge_base_id == knowledge_base_id
        )
    )
    if row is None:
        return CommunitySummaryResponse(
            knowledge_base_id=str(knowledge_base.id),
            knowledge_base_name=knowledge_base.name,
            status=CommunitySummaryStatus.NOT_READY.value,
            prompt_version=COMMUNITY_PROMPT_VERSION,
        )
    return build_community_response(row, knowledge_base)


def build_community_response(
    row: KnowledgeBaseCommunitySummary,
    knowledge_base: KnowledgeBase,
) -> CommunitySummaryResponse:
    return CommunitySummaryResponse(
        knowledge_base_id=str(knowledge_base.id),
        knowledge_base_name=knowledge_base.name,
        status=row.status,
        summary=row.summary,
        document_count=row.document_count,
        model_name=row.model_name,
        prompt_version=row.prompt_version,
        reduction_level=row.reduction_level,
        error_code=row.error_code,
        error_message=row.error_message,
        updated_at=row.updated_at,
    )


class KnowledgeGraphWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        request_semaphore: asyncio.Semaphore,
        settings: Settings | None = None,
        embedding_client: EmbeddingClientProtocol | None = None,
        llm_client: DocumentSummaryLLMClient | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.settings = settings or get_settings()
        self.request_semaphore = request_semaphore
        self.embedding_client = embedding_client
        self.llm_client = llm_client
        self._owns_llm_client = llm_client is None
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    async def start(self) -> None:
        if self._task is not None:
            return
        self.embedding_client = self.embedding_client or get_embedding_client()
        if self.llm_client is None:
            base_url, api_key, model = get_document_summary_llm_config()
            if not base_url or not model:
                logger.warning(
                    "Knowledge graph worker is disabled at runtime because LLM is not configured."
                )
                return
            self.llm_client = DocumentSummaryLLMClient(
                base_url=base_url,
                api_key=api_key,
                model=model,
                settings=self.settings,
                request_semaphore=self.request_semaphore,
            )
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="knowledge-graph-worker")

    async def stop(self) -> None:
        if self._task is not None:
            assert self._stop_event is not None
            self._stop_event.set()
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
            self._stop_event = None
        if self.llm_client is not None and self._owns_llm_client:
            await self.llm_client.aclose()
            self.llm_client = None

    async def _run(self) -> None:
        assert self._stop_event is not None
        assert self.embedding_client is not None
        assert self.llm_client is not None
        while not self._stop_event.is_set():
            try:
                await rebuild_knowledge_graph(
                    session_factory=self.session_factory,
                    settings=self.settings,
                    embedding_client=self.embedding_client,
                    llm_client=self.llm_client,
                )
            except Exception:
                logger.exception("Knowledge graph worker loop failed; it will retry.")
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.settings.knowledge_graph_worker_poll_interval_seconds,
                )
