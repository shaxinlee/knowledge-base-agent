from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql import ColumnElement

from app.models import AuditLog
from app.schemas.audit_logs import AuditLogListResponse, AuditLogResponse


def create_audit_log(
    db: Session,
    *,
    actor_id: UUID,
    action: str,
    resource_type: str,
    resource_id: UUID | None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> AuditLog:
    audit_log = AuditLog(
        actor_user_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details or {},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(audit_log)
    return audit_log


def list_audit_logs(
    db: Session,
    *,
    page: int,
    page_size: int,
    actor_id: UUID | None,
    action: str | None,
    resource_type: str | None,
) -> AuditLogListResponse:
    normalized_page = max(page, 1)
    normalized_page_size = min(max(page_size, 1), 100)
    filters: list[ColumnElement[bool]] = []

    if actor_id is not None:
        filters.append(AuditLog.actor_user_id == actor_id)
    if action:
        filters.append(AuditLog.action == action)
    if resource_type:
        filters.append(AuditLog.resource_type == resource_type)

    base_query = select(AuditLog).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    audit_logs = db.scalars(
        base_query.order_by(AuditLog.created_at.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()

    return AuditLogListResponse(
        items=[build_audit_log_response(audit_log) for audit_log in audit_logs],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


def build_audit_log_response(audit_log: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=str(audit_log.id),
        actor_id=str(audit_log.actor_user_id),
        action=audit_log.action,
        resource_type=audit_log.resource_type,
        resource_id=str(audit_log.resource_id) if audit_log.resource_id else None,
        details=audit_log.details or {},
        created_at=audit_log.created_at,
    )
