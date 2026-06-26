from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas.retrieval import RetrievalSearchRequest, RetrievalSearchResponse
from app.services.bm25_index import BM25IndexClientProtocol, get_bm25_index_client
from app.services.embedding import EmbeddingClientProtocol, get_embedding_client
from app.services.reranker import RerankerClientProtocol, get_reranker_client
from app.services.retrieval import search_knowledge_base
from app.services.vector_index import VectorIndexClientProtocol, get_vector_index_client

router = APIRouter(tags=["Retrieval"])

__all__ = [
    "get_bm25_index_client",
    "get_embedding_client",
    "get_reranker_client",
    "get_vector_index_client",
    "router",
]


@router.post(
    "/knowledge-bases/{knowledge_base_id}/retrieval/search",
    response_model=RetrievalSearchResponse,
)
def search_knowledge_base_endpoint(
    knowledge_base_id: UUID,
    payload: RetrievalSearchRequest,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    embedding_client: EmbeddingClientProtocol = Depends(get_embedding_client),
    reranker_client: RerankerClientProtocol = Depends(get_reranker_client),
    vector_index_client: VectorIndexClientProtocol = Depends(get_vector_index_client),
    bm25_index_client: BM25IndexClientProtocol = Depends(get_bm25_index_client),
) -> RetrievalSearchResponse:
    return search_knowledge_base(
        db,
        knowledge_base_id=knowledge_base_id,
        payload=payload,
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
    )
