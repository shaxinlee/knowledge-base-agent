from datetime import UTC, datetime
from typing import Any, NoReturn
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.core.errors import ApiError
from app.models import ChunkMetadata, File, KnowledgeBase, KnowledgeBaseStatus, User, UserRole
from app.schemas.knowledge_bases import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBasePublicSummaryResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from app.services.audit_logs import create_audit_log

DEFAULT_KNOWLEDGE_BASE_SETTINGS: dict[str, Any] = {
    "default_top_k": 8,
    "strict_citation": True,
    "answer_language": "zh",
}


def list_knowledge_bases(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    status: KnowledgeBaseStatus | None,
    current_user: User,
) -> KnowledgeBaseListResponse:
    normalized_page = max(page, 1)
    normalized_page_size = min(max(page_size, 1), 100)
    filters: list[ColumnElement[bool]] = []

    if current_user.role == UserRole.USER.value:
        filters.append(KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value)
        filters.append(KnowledgeBase.deleted_at.is_(None))
    elif status is not None:
        filters.append(KnowledgeBase.status == status.value)
    else:
        filters.append(KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value)
        filters.append(KnowledgeBase.deleted_at.is_(None))

    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(KnowledgeBase.name.ilike(pattern), KnowledgeBase.description.ilike(pattern))
        )

    base_query = select(KnowledgeBase).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    knowledge_bases = db.scalars(
        base_query.order_by(KnowledgeBase.created_at.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()

    return KnowledgeBaseListResponse(
        items=[
            build_knowledge_base_response(db, knowledge_base) for knowledge_base in knowledge_bases
        ],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


def get_public_knowledge_base_summary(db: Session) -> KnowledgeBasePublicSummaryResponse:
    active_filters = (
        KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
        KnowledgeBase.deleted_at.is_(None),
    )
    active_count = int(
        db.scalar(select(func.count()).select_from(KnowledgeBase).where(*active_filters)) or 0
    )
    earliest_created_at = db.scalar(select(func.min(KnowledgeBase.created_at)).where(*active_filters))
    deployment_day = 1
    if earliest_created_at is not None:
        now = datetime.now(UTC)
        if earliest_created_at.tzinfo is None:
            earliest_created_at = earliest_created_at.replace(tzinfo=UTC)
        deployment_day = max((now.date() - earliest_created_at.date()).days + 1, 1)
    return KnowledgeBasePublicSummaryResponse(
        active_count=active_count,
        deployment_day=deployment_day,
    )


def create_knowledge_base(
    db: Session,
    *,
    payload: KnowledgeBaseCreateRequest,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> KnowledgeBaseResponse:
    knowledge_base = KnowledgeBase(
        name=payload.name,
        description=payload.description,
        status=KnowledgeBaseStatus.ACTIVE.value,
        settings=DEFAULT_KNOWLEDGE_BASE_SETTINGS.copy(),
        created_by=actor.id,
    )
    db.add(knowledge_base)
    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="create_knowledge_base",
        resource_type="knowledge_base",
        resource_id=knowledge_base.id,
        details={"name": knowledge_base.name},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(knowledge_base)
    return build_knowledge_base_response(db, knowledge_base)


def get_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: UUID,
    current_user: User,
) -> KnowledgeBaseResponse:
    knowledge_base = require_visible_knowledge_base(db, knowledge_base_id, current_user)
    return build_knowledge_base_response(db, knowledge_base)


def update_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdateRequest,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> KnowledgeBaseResponse:
    knowledge_base = require_knowledge_base(db, knowledge_base_id)
    before = build_mutation_snapshot(knowledge_base)

    if payload.name is not None:
        knowledge_base.name = payload.name
    if payload.description is not None:
        knowledge_base.description = payload.description
    if payload.status is not None:
        knowledge_base.status = payload.status.value
        if payload.status == KnowledgeBaseStatus.DELETED:
            knowledge_base.deleted_at = knowledge_base.deleted_at or datetime.now(UTC)
        elif payload.status == KnowledgeBaseStatus.ACTIVE:
            knowledge_base.deleted_at = None

    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="update_knowledge_base",
        resource_type="knowledge_base",
        resource_id=knowledge_base.id,
        details={"before": before, "after": build_mutation_snapshot(knowledge_base)},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(knowledge_base)
    return build_knowledge_base_response(db, knowledge_base)


def delete_knowledge_base(
    db: Session,
    *,
    knowledge_base_id: UUID,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    knowledge_base = require_knowledge_base(db, knowledge_base_id)
    before = build_mutation_snapshot(knowledge_base)
    knowledge_base.status = KnowledgeBaseStatus.DELETED.value
    knowledge_base.deleted_at = knowledge_base.deleted_at or datetime.now(UTC)
    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="delete_knowledge_base",
        resource_type="knowledge_base",
        resource_id=knowledge_base.id,
        details={"before": before},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()


def require_visible_knowledge_base(
    db: Session, knowledge_base_id: UUID, current_user: User
) -> KnowledgeBase:
    knowledge_base = require_knowledge_base(db, knowledge_base_id)
    if (
        current_user.role == UserRole.USER.value
        and knowledge_base.status != KnowledgeBaseStatus.ACTIVE.value
    ):
        raise_knowledge_base_not_found()
    return knowledge_base


def require_knowledge_base(db: Session, knowledge_base_id: UUID) -> KnowledgeBase:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        raise_knowledge_base_not_found()
    return knowledge_base


def raise_knowledge_base_not_found() -> NoReturn:
    raise ApiError(
        code="RESOURCE_NOT_FOUND",
        message="Knowledge base was not found.",
        status_code=404,
    )


def build_knowledge_base_response(
    db: Session, knowledge_base: KnowledgeBase
) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=str(knowledge_base.id),
        name=knowledge_base.name,
        description=knowledge_base.description,
        status=knowledge_base.status,
        file_count=count_visible_files(db, knowledge_base_id=knowledge_base.id),
        chunk_count=count_active_chunks(db, knowledge_base_id=knowledge_base.id),
        created_by=str(knowledge_base.created_by),
        created_at=knowledge_base.created_at,
        updated_at=knowledge_base.updated_at,
    )


def count_visible_files(db: Session, *, knowledge_base_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(File)
            .where(File.knowledge_base_id == knowledge_base_id, File.deleted_at.is_(None))
        )
        or 0
    )


def count_active_chunks(db: Session, *, knowledge_base_id: UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ChunkMetadata)
            .join(File, File.id == ChunkMetadata.file_id)
            .where(
                ChunkMetadata.knowledge_base_id == knowledge_base_id,
                ChunkMetadata.is_active.is_(True),
                File.deleted_at.is_(None),
            )
        )
        or 0
    )


def build_mutation_snapshot(knowledge_base: KnowledgeBase) -> dict[str, Any]:
    return {
        "id": str(knowledge_base.id),
        "name": knowledge_base.name,
        "description": knowledge_base.description,
        "status": knowledge_base.status,
    }
