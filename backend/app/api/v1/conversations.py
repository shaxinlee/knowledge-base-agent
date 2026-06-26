import json
from collections.abc import Generator
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.rag.query_router import (
    KnowledgeSearchRouterProtocol,
    QueryRouterProtocol,
    get_knowledge_search_router,
    get_query_router,
)
from app.schemas.conversations import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    MessageCreateRequest,
    MessageCreateResponse,
)
from app.services.bm25_index import BM25IndexClientProtocol, get_bm25_index_client
from app.services.conversations import (
    create_conversation,
    create_message,
    delete_conversation,
    get_message_attachment_asset,
    get_conversation_detail,
    list_conversations,
    stream_create_message_events,
)
from app.services.embedding import EmbeddingClientProtocol, get_embedding_client
from app.services.image_descriptions import (
    ImageDescriptionClientProtocol,
    get_image_description_client,
)
from app.services.llm import LLMClientProtocol, get_llm_client
from app.services.object_storage import ObjectStorage, get_object_storage
from app.services.reranker import RerankerClientProtocol, get_reranker_client
from app.services.vector_index import VectorIndexClientProtocol, get_vector_index_client

router = APIRouter(tags=["Conversations"])

__all__ = [
    "get_embedding_client",
    "get_bm25_index_client",
    "get_llm_client",
    "get_image_description_client",
    "get_knowledge_search_router",
    "get_object_storage",
    "get_query_router",
    "get_reranker_client",
    "get_vector_index_client",
    "router",
]


@router.get("/conversations", response_model=ConversationListResponse)
def read_conversations(
    knowledge_base_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationListResponse:
    return list_conversations(
        db,
        knowledge_base_id=knowledge_base_id,
        page=page,
        page_size=page_size,
        current_user=current_user,
    )


@router.post("/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation_endpoint(
    payload: ConversationCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationResponse:
    return create_conversation(db, payload=payload, current_user=current_user)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def read_conversation_detail(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ConversationDetailResponse:
    return get_conversation_detail(db, conversation_id=conversation_id, current_user=current_user)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation_endpoint(
    conversation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    delete_conversation(db, conversation_id=conversation_id, current_user=current_user)


@router.post("/conversations/{conversation_id}/messages", response_model=None)
def create_conversation_message_endpoint(
    conversation_id: UUID,
    payload: MessageCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    embedding_client: EmbeddingClientProtocol = Depends(get_embedding_client),
    reranker_client: RerankerClientProtocol = Depends(get_reranker_client),
    llm_client: LLMClientProtocol = Depends(get_llm_client),
    vector_index_client: VectorIndexClientProtocol = Depends(get_vector_index_client),
    bm25_index_client: BM25IndexClientProtocol = Depends(get_bm25_index_client),
    storage: ObjectStorage = Depends(get_object_storage),
    image_description_client: ImageDescriptionClientProtocol = Depends(
        get_image_description_client
    ),
    knowledge_search_router: KnowledgeSearchRouterProtocol = Depends(get_knowledge_search_router),
    query_router: QueryRouterProtocol = Depends(get_query_router),
) -> MessageCreateResponse | StreamingResponse:
    if payload.stream:
        return StreamingResponse(
            iter_stream_message_sse_events(
                stream_create_message_events(
                    db,
                    conversation_id=conversation_id,
                    payload=payload,
                    current_user=current_user,
                    embedding_client=embedding_client,
                    reranker_client=reranker_client,
                    llm_client=llm_client,
                    vector_index_client=vector_index_client,
                    bm25_index_client=bm25_index_client,
                    storage=storage,
                    image_description_client=image_description_client,
                    knowledge_search_router=knowledge_search_router,
                    query_router=query_router,
                )
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    response = create_message(
        db,
        conversation_id=conversation_id,
        payload=payload,
        current_user=current_user,
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        llm_client=llm_client,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
        storage=storage,
        image_description_client=image_description_client,
        knowledge_search_router=knowledge_search_router,
        query_router=query_router,
    )
    return response


@router.get("/messages/{message_id}/attachments/{attachment_id}", response_model=None)
def read_message_attachment(
    message_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: ObjectStorage = Depends(get_object_storage),
) -> Response:
    content, media_type = get_message_attachment_asset(
        db,
        message_id=message_id,
        attachment_id=attachment_id,
        current_user=current_user,
        storage=storage,
    )
    return Response(content=content, media_type=media_type)


def iter_stream_message_sse_events(
    events: Generator[tuple[str, dict[str, Any]], None, None],
) -> Generator[str, None, None]:
    for event, data in events:
        yield build_sse_event(event, data)


def iter_message_sse_events(response: MessageCreateResponse) -> Generator[str, None, None]:
    yield build_sse_event(
        "message_created",
        {
            "user_message": response.user_message.model_dump(mode="json"),
            "assistant_message": {
                **response.assistant_message.model_dump(mode="json"),
                "content": "",
            },
        },
    )
    yield build_sse_event(
        "retrieval",
        {
            "retrieved_count": len(response.assistant_message.citations),
            "reranked_count": 0,
            "final_context_count": len(response.assistant_message.citations),
        },
    )
    for token in split_stream_tokens(response.assistant_message.content):
        yield build_sse_event("token", {"text": token})
    yield build_sse_event(
        "done",
        {
            "message_id": response.assistant_message.id,
            "answer": response.assistant_message.content,
            "citations": [
                citation.model_dump(mode="json")
                for citation in response.assistant_message.citations
            ],
        },
    )


def split_stream_tokens(content: str) -> Generator[str, None, None]:
    chunk_size = 16
    for index in range(0, len(content), chunk_size):
        yield content[index : index + chunk_size]


def build_sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
