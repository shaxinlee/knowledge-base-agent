from datetime import UTC, datetime
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import (
    Conversation,
    ConversationStatus,
    Feedback,
    Message,
    MessageCitation,
    MessageRole,
    MessageTrace,
    User,
)
from app.schemas.conversations import (
    CitationResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationResponse,
    MessageCreateRequest,
    MessageCreateResponse,
    MessageResponse,
)
from app.schemas.retrieval import RetrievalResultItem, RetrievalSearchRequest
from app.services.bm25_index import BM25IndexClientProtocol
from app.services.embedding import EmbeddingClientProtocol
from app.services.llm import LLMClientProtocol, build_refusal_answer
from app.services.reranker import RerankerClientProtocol
from app.services.retrieval import require_active_knowledge_base, search_knowledge_base
from app.services.vector_index import VectorIndexClientProtocol


def list_conversations(
    db: Session,
    *,
    knowledge_base_id: UUID,
    page: int,
    page_size: int,
    current_user: User,
) -> ConversationListResponse:
    normalized_page = max(page, 1)
    normalized_page_size = min(max(page_size, 1), 100)
    base_query = select(Conversation).where(
        Conversation.user_id == current_user.id,
        Conversation.knowledge_base_id == knowledge_base_id,
        Conversation.status == ConversationStatus.ACTIVE.value,
        Conversation.deleted_at.is_(None),
    )
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    conversations = db.scalars(
        base_query.order_by(Conversation.updated_at.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()
    return ConversationListResponse(
        items=[build_conversation_response(conversation) for conversation in conversations],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


def create_conversation(
    db: Session,
    *,
    payload: ConversationCreateRequest,
    current_user: User,
) -> ConversationResponse:
    knowledge_base_id = parse_uuid(payload.knowledge_base_id, "knowledge_base_id")
    require_active_knowledge_base(db, knowledge_base_id)
    conversation = Conversation(
        user_id=current_user.id,
        knowledge_base_id=knowledge_base_id,
        title=payload.title,
        status=ConversationStatus.ACTIVE.value,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return build_conversation_response(conversation)


def get_conversation_detail(
    db: Session,
    *,
    conversation_id: UUID,
    current_user: User,
) -> ConversationDetailResponse:
    conversation = require_user_conversation(db, conversation_id, current_user)
    messages = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ).all()
    citations = load_citations_for_messages(db, [message.id for message in messages])
    feedback_ratings = load_feedback_ratings_for_messages(
        db,
        message_ids=[message.id for message in messages],
        current_user=current_user,
    )
    return ConversationDetailResponse(
        **build_conversation_response(conversation).model_dump(),
        messages=[
            build_message_response(
                message,
                citations.get(message.id, []),
                feedback_rating=feedback_ratings.get(message.id),
            )
            for message in messages
        ],
    )


def delete_conversation(
    db: Session,
    *,
    conversation_id: UUID,
    current_user: User,
) -> None:
    conversation = require_user_conversation(db, conversation_id, current_user)
    now = datetime.now(UTC)
    conversation.status = ConversationStatus.DELETED.value
    conversation.deleted_at = conversation.deleted_at or now
    conversation.updated_at = now
    db.commit()


def create_message(
    db: Session,
    *,
    conversation_id: UUID,
    payload: MessageCreateRequest,
    current_user: User,
    embedding_client: EmbeddingClientProtocol,
    reranker_client: RerankerClientProtocol,
    llm_client: LLMClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
) -> MessageCreateResponse:
    conversation = require_user_conversation(db, conversation_id, current_user)
    query_text = payload.content.strip()
    if not query_text:
        raise ApiError(
            code="VALIDATION_ERROR", message="Message content cannot be empty.", status_code=422
        )

    user_message = Message(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=MessageRole.USER.value,
        content=query_text,
        status="completed",
    )
    db.add(user_message)
    db.flush()

    retrieval_response = search_knowledge_base(
        db,
        knowledge_base_id=conversation.knowledge_base_id,
        payload=RetrievalSearchRequest(query=query_text, top_k=6),
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
    )
    final_context_items = apply_evidence_gate(retrieval_response.items)
    if final_context_items:
        llm_answer = llm_client.generate_answer(
            query=query_text,
            contexts=final_context_items,
        )
        assistant_content = llm_answer.content
        chat_model = llm_answer.model
        prompt_version = llm_answer.prompt_version
        raw_prompt_snapshot = llm_answer.raw_prompt_snapshot
        token_usage = llm_answer.token_usage
    else:
        assistant_content = build_refusal_answer()
        chat_model = llm_client.model
        prompt_version = llm_client.prompt_version
        raw_prompt_snapshot = None
        token_usage = {}
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=MessageRole.ASSISTANT.value,
        content=assistant_content,
        status="completed",
        model_name=chat_model,
        prompt_version=prompt_version,
    )
    db.add(assistant_message)
    db.flush()

    citation_rows: list[MessageCitation] = []
    for index, item in enumerate(final_context_items, start=1):
        citation = MessageCitation(
            message_id=assistant_message.id,
            chunk_id=UUID(item.chunk_id),
            file_id=UUID(item.file_id),
            citation_index=index,
            source_label=item.file_name,
            excerpt=item.excerpt,
            source_locator=item.source_locator,
        )
        db.add(citation)
        citation_rows.append(citation)

    cited_chunk_ids = [item.chunk_id for item in final_context_items]
    db.add(
        MessageTrace(
            message_id=assistant_message.id,
            query_text=query_text,
            retrieved_chunk_ids=[item.chunk_id for item in retrieval_response.items],
            reranked_chunk_ids=[item.chunk_id for item in retrieval_response.items],
            final_context_chunk_ids=cited_chunk_ids,
            final_cited_chunk_ids=cited_chunk_ids,
            reranker_scores=build_reranker_scores(retrieval_response.items),
            embedding_model=embedding_client.model,
            reranker_model=reranker_client.model,
            chat_model=chat_model,
            prompt_version=prompt_version,
            latency_breakdown={},
            token_usage=token_usage,
            raw_prompt_snapshot=raw_prompt_snapshot,
        )
    )
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    for citation in citation_rows:
        db.refresh(citation)

    return MessageCreateResponse(
        user_message=build_message_response(user_message, []),
        assistant_message=build_message_response(
            assistant_message,
            [build_citation_response(citation) for citation in citation_rows],
        ),
    )


def build_reranker_scores(items: Sequence[RetrievalResultItem]) -> dict[str, float]:
    return {item.chunk_id: item.score for item in items}


def apply_evidence_gate(items: Sequence[RetrievalResultItem]) -> list[RetrievalResultItem]:
    contexts = list(items[:6])
    if not contexts:
        return []
    threshold = get_settings().evidence_min_reranker_score
    if threshold is None:
        return contexts
    highest_score = max(item.score for item in contexts)
    if highest_score < threshold:
        return []
    return contexts


def require_user_conversation(
    db: Session,
    conversation_id: UUID,
    current_user: User,
) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if (
        conversation is None
        or conversation.user_id != current_user.id
        or conversation.status != ConversationStatus.ACTIVE.value
        or conversation.deleted_at is not None
    ):
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Conversation was not found.",
            status_code=404,
        )
    return conversation


def parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ApiError(
            code="VALIDATION_ERROR",
            message=f"{field_name} must be a valid UUID.",
            status_code=422,
        ) from exc


def load_citations_for_messages(
    db: Session, message_ids: list[UUID]
) -> dict[UUID, list[CitationResponse]]:
    if not message_ids:
        return {}
    citation_rows = db.scalars(
        select(MessageCitation)
        .where(MessageCitation.message_id.in_(message_ids))
        .order_by(MessageCitation.citation_index)
    ).all()
    citations: dict[UUID, list[CitationResponse]] = {}
    for citation in citation_rows:
        citations.setdefault(citation.message_id, []).append(build_citation_response(citation))
    return citations


def load_feedback_ratings_for_messages(
    db: Session,
    *,
    message_ids: list[UUID],
    current_user: User,
) -> dict[UUID, str]:
    if not message_ids:
        return {}
    feedback_rows = db.scalars(
        select(Feedback).where(
            Feedback.message_id.in_(message_ids),
            Feedback.user_id == current_user.id,
        )
    ).all()
    return {feedback.message_id: feedback.rating for feedback in feedback_rows}


def build_conversation_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse(
        id=str(conversation.id),
        knowledge_base_id=str(conversation.knowledge_base_id),
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def build_message_response(
    message: Message,
    citations: list[CitationResponse],
    *,
    feedback_rating: str | None = None,
) -> MessageResponse:
    return MessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id),
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        citations=citations,
        feedback_rating=feedback_rating,
    )


def build_citation_response(citation: MessageCitation) -> CitationResponse:
    return CitationResponse(
        id=str(citation.id),
        index=citation.citation_index,
        file_name=citation.source_label or "",
        source_locator=citation.source_locator,
        excerpt=citation.excerpt,
        chunk_id=str(citation.chunk_id),
    )
