from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin_user
from app.db.session import get_db
from app.models import KnowledgeBaseStatus, User
from app.schemas.knowledge_bases import (
    KnowledgeBaseCreateRequest,
    KnowledgeBaseListResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdateRequest,
)
from app.services.knowledge_bases import (
    create_knowledge_base,
    delete_knowledge_base,
    get_knowledge_base,
    list_knowledge_bases,
    update_knowledge_base,
)

router = APIRouter(prefix="/knowledge-bases", tags=["KnowledgeBases"])


@router.get("", response_model=KnowledgeBaseListResponse)
def read_knowledge_bases(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = None,
    status: KnowledgeBaseStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseListResponse:
    return list_knowledge_bases(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        status=status,
        current_user=current_user,
    )


@router.post("", response_model=KnowledgeBaseResponse, status_code=201)
def create_knowledge_base_endpoint(
    payload: KnowledgeBaseCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> KnowledgeBaseResponse:
    return create_knowledge_base(
        db,
        payload=payload,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.get("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
def read_knowledge_base(
    knowledge_base_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> KnowledgeBaseResponse:
    return get_knowledge_base(db, knowledge_base_id=knowledge_base_id, current_user=current_user)


@router.patch("/{knowledge_base_id}", response_model=KnowledgeBaseResponse)
def update_knowledge_base_endpoint(
    knowledge_base_id: UUID,
    payload: KnowledgeBaseUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> KnowledgeBaseResponse:
    return update_knowledge_base(
        db,
        knowledge_base_id=knowledge_base_id,
        payload=payload,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.delete("/{knowledge_base_id}", status_code=204)
def delete_knowledge_base_endpoint(
    knowledge_base_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> Response:
    delete_knowledge_base(
        db,
        knowledge_base_id=knowledge_base_id,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(status_code=204)


def get_request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
