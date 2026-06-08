from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import require_admin_user
from app.db.session import get_db
from app.models import User
from app.schemas.audit_logs import AuditLogListResponse
from app.services.audit_logs import list_audit_logs

router = APIRouter(prefix="/audit-logs", tags=["AuditLogs"])


@router.get("", response_model=AuditLogListResponse)
def read_audit_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor_id: UUID | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> AuditLogListResponse:
    return list_audit_logs(
        db,
        page=page,
        page_size=page_size,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
    )
