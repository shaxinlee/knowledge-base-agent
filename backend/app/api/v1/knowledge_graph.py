from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_admin_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.schemas.knowledge_graph import (
    KnowledgeGraphRefreshRequest,
    KnowledgeGraphResponse,
)
from app.services.knowledge_graph import (
    get_knowledge_graph_response,
    request_knowledge_graph_refresh,
)

router = APIRouter(prefix="/knowledge-graph", tags=["KnowledgeGraph"])


@router.get("", response_model=KnowledgeGraphResponse)
def read_knowledge_graph(
    knowledge_base_id: UUID | None = None,
    include_cross_knowledge_base: bool = True,
    min_similarity: float = Query(default=0.45, ge=0, le=1),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> KnowledgeGraphResponse:
    return get_knowledge_graph_response(
        db,
        knowledge_base_id=knowledge_base_id,
        include_cross_knowledge_base=include_cross_knowledge_base,
        min_similarity=min_similarity,
    )


@router.post("/refresh", response_model=KnowledgeGraphResponse, status_code=202)
def refresh_knowledge_graph(
    payload: KnowledgeGraphRefreshRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> KnowledgeGraphResponse:
    request_knowledge_graph_refresh(db, force_embeddings=payload.force_embeddings)
    return get_knowledge_graph_response(
        db,
        knowledge_base_id=None,
        include_cross_knowledge_base=True,
        min_similarity=get_settings().knowledge_graph_similarity_threshold,
    )
