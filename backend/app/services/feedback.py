from datetime import UTC, datetime
from typing import NoReturn
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import (
    Conversation,
    Feedback,
    Message,
    MessageRole,
    MessageTrace,
    User,
)
from app.schemas.feedback import FeedbackCreateRequest, FeedbackResponse


def create_or_update_feedback(
    db: Session,
    *,
    message_id: UUID,
    payload: FeedbackCreateRequest,
    current_user: User,
) -> FeedbackResponse:
    message = db.get(Message, message_id)
    if message is None or message.user_id != current_user.id:
        raise_feedback_target_not_found()
    if message.role != MessageRole.ASSISTANT.value:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Feedback can only be submitted for assistant messages.",
            status_code=422,
        )

    conversation = db.get(Conversation, message.conversation_id)
    if conversation is None or conversation.user_id != current_user.id:
        raise_feedback_target_not_found()

    trace = db.scalar(select(MessageTrace).where(MessageTrace.message_id == message.id))
    feedback = db.scalar(
        select(Feedback).where(
            Feedback.message_id == message.id,
            Feedback.user_id == current_user.id,
        )
    )
    if feedback is None:
        feedback = Feedback(
            message_id=message.id,
            user_id=current_user.id,
            knowledge_base_id=conversation.knowledge_base_id,
        )
        db.add(feedback)

    feedback.rating = payload.rating.value
    feedback.comment = payload.comment
    feedback.query_text = trace.query_text if trace else None
    feedback.retrieved_chunk_ids = trace.retrieved_chunk_ids if trace else None
    feedback.final_cited_chunk_ids = trace.final_cited_chunk_ids if trace else None
    feedback.model_name = message.model_name or (trace.chat_model if trace else None)
    feedback.prompt_version = message.prompt_version or (trace.prompt_version if trace else None)
    feedback.embedding_model = trace.embedding_model if trace else None
    feedback.reranker_model = trace.reranker_model if trace else None
    feedback.latency_ms = message.latency_ms
    feedback.token_input = message.token_input
    feedback.token_output = message.token_output
    feedback.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(feedback)
    return build_feedback_response(feedback)


def build_feedback_response(feedback: Feedback) -> FeedbackResponse:
    return FeedbackResponse(
        id=str(feedback.id),
        message_id=str(feedback.message_id),
        user_id=str(feedback.user_id),
        knowledge_base_id=str(feedback.knowledge_base_id),
        rating=feedback.rating,
        comment=feedback.comment,
        query_text=feedback.query_text,
        retrieved_chunk_ids=feedback.retrieved_chunk_ids,
        final_cited_chunk_ids=feedback.final_cited_chunk_ids,
        model_name=feedback.model_name,
        prompt_version=feedback.prompt_version,
        embedding_model=feedback.embedding_model,
        reranker_model=feedback.reranker_model,
        latency_ms=feedback.latency_ms,
        token_input=feedback.token_input,
        token_output=feedback.token_output,
        created_at=feedback.created_at,
        updated_at=feedback.updated_at,
    )


def raise_feedback_target_not_found() -> NoReturn:
    raise ApiError(
        code="RESOURCE_NOT_FOUND",
        message="Message was not found.",
        status_code=404,
    )
