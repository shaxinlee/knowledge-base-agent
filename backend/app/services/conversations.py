import base64
import binascii
import hashlib
import re
from collections.abc import Generator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import (
    ChunkMetadata,
    Conversation,
    ConversationStatus,
    Feedback,
    File,
    FileStatus,
    Message,
    MessageAttachment,
    MessageCitation,
    MessageRole,
    MessageTrace,
    User,
)
from app.rag.query_router import (
    KnowledgeSearchDecision,
    KnowledgeSearchRouterProtocol,
    QueryRouterProtocol,
    RouteDecision,
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
    MessageAttachmentInput,
    MessageAttachmentResponse,
)
from app.schemas.retrieval import RetrievalResultItem, RetrievalSearchRequest
from app.services.bm25_index import BM25IndexClientProtocol
from app.services.chunk_text import build_display_chunk_text
from app.services.content_normalization import normalize_special_elements
from app.services.embedding import EmbeddingClientProtocol
from app.services.image_descriptions import ImageDescriptionClientProtocol, ImageDescriptionInput
from app.services.llm import DIRECT_PROMPT_VERSION, LLMClientProtocol, build_refusal_answer
from app.services.object_storage import ObjectStorage
from app.services.reranker import RerankerClientProtocol
from app.services.retrieval import require_active_knowledge_base, search_knowledge_base
from app.services.vector_index import VectorIndexClientProtocol
from app.services.visual_citations import (
    build_chunk_image_alt,
    build_chunk_image_url,
    build_chunk_image_urls,
    infer_chunk_modality,
    strip_visible_image_references,
)


@dataclass
class MessageContext:
    conversation: Conversation
    user_message: Message
    user_attachments: list[MessageAttachment]
    query_text: str
    query_image_vector: list[float] | None
    knowledge_search_decision: KnowledgeSearchDecision
    route_decision: RouteDecision | None
    retrieval_items: list[RetrievalResultItem]
    final_context_items: list[RetrievalResultItem]


@dataclass(frozen=True)
class DecodedMessageAttachment:
    input: MessageAttachmentInput
    data: bytes


DEFAULT_IMAGE_QUERY_TEXT = "请分析这张图片并检索相关知识库内容"
ALLOWED_MESSAGE_IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
DATA_URL_PATTERN = re.compile(r"^data:(?P<media_type>[-\w.]+/[-\w.+]+);base64,(?P<data>.+)$", re.S)


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
    attachments = load_attachments_for_messages(db, [message.id for message in messages])
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
                attachments=attachments.get(message.id, []),
                feedback_rating=feedback_ratings.get(message.id),
                visual_result_mode=infer_message_visual_result_mode(citations.get(message.id, [])),
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
    storage: ObjectStorage,
    image_description_client: ImageDescriptionClientProtocol,
    knowledge_search_router: KnowledgeSearchRouterProtocol,
    query_router: QueryRouterProtocol,
) -> MessageCreateResponse:
    message_context = prepare_message_context(
        db,
        conversation_id=conversation_id,
        payload=payload,
        current_user=current_user,
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
        storage=storage,
        image_description_client=image_description_client,
        knowledge_search_router=knowledge_search_router,
        query_router=query_router,
    )
    if not message_context.knowledge_search_decision.research_base:
        if message_context.knowledge_search_decision.direct_answer:
            assistant_content = sanitize_visible_text(
                message_context.knowledge_search_decision.direct_answer
            )
            chat_model = llm_client.model
            prompt_version = "assistant-profile-v1"
            raw_prompt_snapshot = None
            token_usage = {}
        else:
            llm_answer = llm_client.generate_direct_answer(query=message_context.query_text)
            assistant_content = sanitize_visible_text(llm_answer.content)
            chat_model = llm_answer.model
            prompt_version = llm_answer.prompt_version
            raw_prompt_snapshot = llm_answer.raw_prompt_snapshot
            token_usage = llm_answer.token_usage
    elif message_context.final_context_items:
        llm_answer = llm_client.generate_answer(
            query=message_context.query_text,
            contexts=message_context.final_context_items,
        )
        assistant_content = sanitize_visible_text(llm_answer.content)
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

    assistant_message, citation_rows = save_assistant_message(
        db,
        conversation=message_context.conversation,
        current_user=current_user,
        content=assistant_content,
        model_name=chat_model,
        prompt_version=prompt_version,
        final_context_items=message_context.final_context_items,
        allow_images=bool(
            message_context.route_decision and message_context.route_decision.search_image_vector
        ),
    )
    save_message_trace(
        db,
        assistant_message=assistant_message,
        query_text=message_context.query_text,
        retrieval_items=message_context.retrieval_items,
        final_context_items=message_context.final_context_items,
        embedding_model=embedding_client.model,
        reranker_model=reranker_client.model,
        chat_model=chat_model,
        prompt_version=prompt_version,
        token_usage=token_usage,
        raw_prompt_snapshot=raw_prompt_snapshot,
    )
    message_context.conversation.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(message_context.user_message)
    db.refresh(assistant_message)
    for citation in citation_rows:
        db.refresh(citation)

    return MessageCreateResponse(
        user_message=build_message_response(
            message_context.user_message,
            [],
            attachments=build_attachment_responses(message_context.user_attachments),
        ),
        assistant_message=build_message_response(
            assistant_message,
            [
                build_citation_response(
                    citation,
                    context_item=message_context.final_context_items[index],
                    allow_images=bool(
                        message_context.route_decision
                        and message_context.route_decision.search_image_vector
                    ),
                )
                for index, citation in enumerate(citation_rows)
            ],
            visual_result_mode=message_context.route_decision.visual_result_mode
            if message_context.route_decision
            else None,
        ),
    )


def stream_create_message_events(
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
    storage: ObjectStorage,
    image_description_client: ImageDescriptionClientProtocol,
    knowledge_search_router: KnowledgeSearchRouterProtocol,
    query_router: QueryRouterProtocol,
) -> Generator[tuple[str, dict[str, Any]], None, None]:
    conversation = require_user_conversation(db, conversation_id, current_user)
    decoded_attachments = decode_message_attachments(payload.attachments)
    query_text = normalize_message_query(payload.content, decoded_attachments)

    user_message = Message(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=MessageRole.USER.value,
        content=query_text,
        status="completed",
    )
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=MessageRole.ASSISTANT.value,
        content="",
        status="streaming",
        model_name=llm_client.model,
        prompt_version=llm_client.prompt_version,
    )
    db.add(user_message)
    db.add(assistant_message)
    db.flush()
    user_attachments = save_message_attachments(
        db,
        message=user_message,
        attachments=decoded_attachments,
        storage=storage,
    )
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(user_message)
    db.refresh(assistant_message)
    for attachment in user_attachments:
        db.refresh(attachment)

    yield (
        "message_created",
        {
            "user_message": build_message_response(
                user_message,
                [],
                attachments=build_attachment_responses(user_attachments),
            ).model_dump(mode="json"),
            "assistant_message": build_message_response(assistant_message, []).model_dump(
                mode="json"
            ),
        },
    )

    query_image_vector, augmented_query_text = build_multimodal_query_inputs(
        query_text=query_text,
        attachments=decoded_attachments,
        embedding_client=embedding_client,
        image_description_client=image_description_client,
    )

    knowledge_search_decision = knowledge_search_router.decide(augmented_query_text)
    if not knowledge_search_decision.research_base:
        yield (
            "retrieval",
            {"retrieved_count": 0, "reranked_count": 0, "final_context_count": 0},
        )
        assistant_content = ""
        if knowledge_search_decision.direct_answer:
            token_source = split_stream_text(knowledge_search_decision.direct_answer)
            prompt_version = "assistant-profile-v1"
        else:
            token_source = llm_client.stream_direct_answer(query=augmented_query_text)
            prompt_version = DIRECT_PROMPT_VERSION
        for token in token_source:
            safe_token = sanitize_visible_text(token)
            assistant_content += safe_token
            if safe_token:
                yield ("token", {"text": safe_token})

        assistant_content = sanitize_visible_text(assistant_content)
        assistant_message.content = assistant_content
        assistant_message.status = "completed"
        assistant_message.model_name = llm_client.model
        assistant_message.prompt_version = prompt_version
        save_message_trace(
            db,
            assistant_message=assistant_message,
            query_text=augmented_query_text,
            retrieval_items=[],
            final_context_items=[],
            embedding_model=embedding_client.model,
            reranker_model=reranker_client.model,
            chat_model=llm_client.model,
            prompt_version=prompt_version,
            token_usage={},
            raw_prompt_snapshot=None,
        )
        conversation.updated_at = datetime.now(UTC)
        db.commit()
        db.refresh(assistant_message)
        yield (
            "done",
            {
                "message_id": str(assistant_message.id),
                "answer": assistant_content,
                "citations": [],
                "visual_result_mode": None,
            },
        )
        return

    route_decision = query_router.route(augmented_query_text)
    retrieval_response = search_knowledge_base(
        db,
        knowledge_base_id=conversation.knowledge_base_id,
        payload=build_routed_retrieval_request(
            query=augmented_query_text,
            route_decision=route_decision,
            query_image_vector=query_image_vector,
        ),
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
    )
    routed_items = apply_route_preferences(retrieval_response.items, route_decision=route_decision)
    gated_context_items = apply_evidence_gate(routed_items, route_decision=route_decision)
    final_context_items = expand_context_to_section_chunks(
        db,
        knowledge_base_id=conversation.knowledge_base_id,
        items=gated_context_items,
    )
    final_context_items = apply_image_display_policy(
        final_context_items,
        route_decision=route_decision,
    )

    yield (
        "retrieval",
        {
            "retrieved_count": len(retrieval_response.items),
            "reranked_count": len(retrieval_response.items),
            "final_context_count": len(final_context_items),
        },
    )

    assistant_content = ""
    if final_context_items:
        for token in llm_client.stream_answer(
            query=augmented_query_text,
            contexts=final_context_items,
        ):
            safe_token = sanitize_visible_text(token)
            assistant_content += safe_token
            if safe_token:
                yield ("token", {"text": safe_token})
    else:
        for token in split_stream_text(build_refusal_answer()):
            safe_token = sanitize_visible_text(token)
            assistant_content += safe_token
            if safe_token:
                yield ("token", {"text": safe_token})

    assistant_content = sanitize_visible_text(assistant_content)
    assistant_message.content = assistant_content
    assistant_message.status = "completed"
    assistant_message.model_name = llm_client.model
    assistant_message.prompt_version = llm_client.prompt_version
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
            allow_images=route_decision.search_image_vector,
        )
        db.add(citation)
        citation_rows.append(citation)

    save_message_trace(
        db,
        assistant_message=assistant_message,
        query_text=query_text,
        retrieval_items=retrieval_response.items,
        final_context_items=final_context_items,
        embedding_model=embedding_client.model,
        reranker_model=reranker_client.model,
        chat_model=llm_client.model,
        prompt_version=llm_client.prompt_version,
        token_usage={},
        raw_prompt_snapshot=None,
    )
    conversation.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(assistant_message)
    for citation in citation_rows:
        db.refresh(citation)

    yield (
        "done",
        {
            "message_id": str(assistant_message.id),
            "answer": assistant_content,
            "citations": [
                build_citation_response(
                    citation,
                    context_item=final_context_items[index],
                    allow_images=route_decision.search_image_vector,
                ).model_dump(mode="json")
                for index, citation in enumerate(citation_rows)
            ],
            "visual_result_mode": route_decision.visual_result_mode,
        },
    )


def prepare_message_context(
    db: Session,
    *,
    conversation_id: UUID,
    payload: MessageCreateRequest,
    current_user: User,
    embedding_client: EmbeddingClientProtocol,
    reranker_client: RerankerClientProtocol,
    vector_index_client: VectorIndexClientProtocol,
    bm25_index_client: BM25IndexClientProtocol,
    storage: ObjectStorage,
    image_description_client: ImageDescriptionClientProtocol,
    knowledge_search_router: KnowledgeSearchRouterProtocol,
    query_router: QueryRouterProtocol,
) -> MessageContext:
    conversation = require_user_conversation(db, conversation_id, current_user)
    decoded_attachments = decode_message_attachments(payload.attachments)
    query_text = normalize_message_query(payload.content, decoded_attachments)

    user_message = Message(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=MessageRole.USER.value,
        content=query_text,
        status="completed",
    )
    db.add(user_message)
    db.flush()
    user_attachments = save_message_attachments(
        db,
        message=user_message,
        attachments=decoded_attachments,
        storage=storage,
    )

    query_image_vector, augmented_query_text = build_multimodal_query_inputs(
        query_text=query_text,
        attachments=decoded_attachments,
        embedding_client=embedding_client,
        image_description_client=image_description_client,
    )

    knowledge_search_decision = knowledge_search_router.decide(augmented_query_text)
    if not knowledge_search_decision.research_base:
        return MessageContext(
            conversation=conversation,
            user_message=user_message,
            user_attachments=user_attachments,
            query_text=augmented_query_text,
            query_image_vector=query_image_vector,
            knowledge_search_decision=knowledge_search_decision,
            route_decision=None,
            retrieval_items=[],
            final_context_items=[],
        )

    route_decision = query_router.route(augmented_query_text)
    retrieval_response = search_knowledge_base(
        db,
        knowledge_base_id=conversation.knowledge_base_id,
        payload=build_routed_retrieval_request(
            query=augmented_query_text,
            route_decision=route_decision,
            query_image_vector=query_image_vector,
        ),
        embedding_client=embedding_client,
        reranker_client=reranker_client,
        vector_index_client=vector_index_client,
        bm25_index_client=bm25_index_client,
    )
    routed_items = apply_route_preferences(retrieval_response.items, route_decision=route_decision)
    gated_context_items = apply_evidence_gate(routed_items, route_decision=route_decision)
    final_context_items = expand_context_to_section_chunks(
        db,
        knowledge_base_id=conversation.knowledge_base_id,
        items=gated_context_items,
    )
    final_context_items = apply_image_display_policy(
        final_context_items,
        route_decision=route_decision,
    )
    return MessageContext(
        conversation=conversation,
        user_message=user_message,
        user_attachments=user_attachments,
        query_text=augmented_query_text,
        query_image_vector=query_image_vector,
        knowledge_search_decision=knowledge_search_decision,
        route_decision=route_decision,
        retrieval_items=list(retrieval_response.items),
        final_context_items=final_context_items,
    )


def save_assistant_message(
    db: Session,
    *,
    conversation: Conversation,
    current_user: User,
    content: str,
    model_name: str,
    prompt_version: str,
    final_context_items: Sequence[RetrievalResultItem],
    allow_images: bool,
) -> tuple[Message, list[MessageCitation]]:
    assistant_message = Message(
        conversation_id=conversation.id,
        user_id=current_user.id,
        role=MessageRole.ASSISTANT.value,
        content=content,
        status="completed",
        model_name=model_name,
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
            allow_images=allow_images,
        )
        db.add(citation)
        citation_rows.append(citation)
    return assistant_message, citation_rows


def save_message_trace(
    db: Session,
    *,
    assistant_message: Message,
    query_text: str,
    retrieval_items: Sequence[RetrievalResultItem],
    final_context_items: Sequence[RetrievalResultItem],
    embedding_model: str,
    reranker_model: str,
    chat_model: str,
    prompt_version: str,
    token_usage: dict[str, Any],
    raw_prompt_snapshot: str | None,
) -> None:
    cited_chunk_ids = [item.chunk_id for item in final_context_items]
    db.add(
        MessageTrace(
            message_id=assistant_message.id,
            query_text=query_text,
            retrieved_chunk_ids=[item.chunk_id for item in retrieval_items],
            reranked_chunk_ids=[item.chunk_id for item in retrieval_items],
            final_context_chunk_ids=cited_chunk_ids,
            final_cited_chunk_ids=cited_chunk_ids,
            reranker_scores=build_reranker_scores(retrieval_items),
            embedding_model=embedding_model,
            reranker_model=reranker_model,
            chat_model=chat_model,
            prompt_version=prompt_version,
            latency_breakdown={},
            token_usage=token_usage,
            raw_prompt_snapshot=raw_prompt_snapshot,
        )
    )


def decode_message_attachments(
    attachments: Sequence[MessageAttachmentInput],
) -> list[DecodedMessageAttachment]:
    if len(attachments) > 1:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Only one image attachment is supported per message.",
            status_code=422,
        )
    decoded: list[DecodedMessageAttachment] = []
    for attachment in attachments:
        if attachment.type != "image":
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Only image attachments are supported.",
                status_code=422,
            )
        match = DATA_URL_PATTERN.match(attachment.data_url)
        if match is None:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Image attachment must be a base64 data URL.",
                status_code=422,
            )
        media_type = match.group("media_type").lower()
        if media_type not in ALLOWED_MESSAGE_IMAGE_MEDIA_TYPES:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Unsupported image attachment type.",
                status_code=422,
                details={"media_type": media_type},
            )
        if attachment.media_type.lower() != media_type:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Image attachment media type does not match data URL.",
                status_code=422,
            )
        try:
            data = base64.b64decode(match.group("data"), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Image attachment data is not valid base64.",
                status_code=422,
            ) from exc
        max_size = get_settings().max_message_attachment_size_mb * 1024 * 1024
        if len(data) > max_size:
            raise ApiError(
                code="VALIDATION_ERROR",
                message="Image attachment is too large.",
                status_code=422,
                details={"max_size_bytes": max_size},
            )
        decoded.append(DecodedMessageAttachment(input=attachment, data=data))
    return decoded


def normalize_message_query(
    content: str,
    attachments: Sequence[DecodedMessageAttachment],
) -> str:
    query_text = content.strip()
    if query_text:
        return query_text
    if attachments:
        return DEFAULT_IMAGE_QUERY_TEXT
    raise ApiError(
        code="VALIDATION_ERROR",
        message="Message content or image attachment is required.",
        status_code=422,
    )


def save_message_attachments(
    db: Session,
    *,
    message: Message,
    attachments: Sequence[DecodedMessageAttachment],
    storage: ObjectStorage,
) -> list[MessageAttachment]:
    saved: list[MessageAttachment] = []
    settings = get_settings()
    for attachment in attachments:
        digest = hashlib.sha256(attachment.data).hexdigest()
        key = f"messages/{message.conversation_id}/{message.id}/{uuid4()}-{digest[:16]}"
        storage.put_object(
            bucket=settings.message_attachments_bucket,
            key=key,
            data=attachment.data,
            content_type=attachment.input.media_type,
            metadata={"message_id": str(message.id)},
        )
        row = MessageAttachment(
            message_id=message.id,
            attachment_type=attachment.input.type,
            file_name=attachment.input.file_name,
            media_type=attachment.input.media_type,
            size_bytes=len(attachment.data),
            storage_bucket=settings.message_attachments_bucket,
            storage_key=key,
        )
        db.add(row)
        saved.append(row)
    return saved


def build_multimodal_query_inputs(
    *,
    query_text: str,
    attachments: Sequence[DecodedMessageAttachment],
    embedding_client: EmbeddingClientProtocol,
    image_description_client: ImageDescriptionClientProtocol,
) -> tuple[list[float] | None, str]:
    if not attachments:
        return None, query_text
    attachment = attachments[0]
    routed_query_text = f"{query_text}\n\n用户上传图片：作为视觉检索条件。"
    image_vector = try_embed_query_image(embedding_client, attachment.input.data_url)
    if image_vector is not None:
        return image_vector, routed_query_text
    description = try_describe_query_image(
        image_description_client=image_description_client,
        attachment=attachment,
        query_text=query_text,
    )
    if not description:
        return None, routed_query_text
    return None, f"{routed_query_text}\n\n用户上传图片描述：{description}"


def try_embed_query_image(
    embedding_client: EmbeddingClientProtocol,
    data_url: str,
) -> list[float] | None:
    try:
        vectors = embedding_client.embed_images([data_url])
    except (ApiError, AttributeError):
        return None
    return vectors[0] if vectors else None


def try_describe_query_image(
    *,
    image_description_client: ImageDescriptionClientProtocol,
    attachment: DecodedMessageAttachment,
    query_text: str,
) -> str:
    if not image_description_client.enabled:
        return ""
    try:
        return image_description_client.describe_image(
            ImageDescriptionInput(
                image_bytes=attachment.data,
                media_type=attachment.input.media_type,
                context_text=query_text,
                source_locator="user-message-attachment",
                file_name=attachment.input.file_name,
            )
        )
    except ApiError:
        return ""


def split_stream_text(content: str) -> Generator[str, None, None]:
    chunk_size = 16
    for index in range(0, len(content), chunk_size):
        yield content[index : index + chunk_size]


def build_reranker_scores(items: Sequence[RetrievalResultItem]) -> dict[str, float]:
    return {item.chunk_id: item.score for item in items}


def build_routed_retrieval_request(
    *,
    query: str,
    route_decision: RouteDecision,
    query_image_vector: list[float] | None = None,
) -> RetrievalSearchRequest:
    enabled_routes = [route for route in route_decision.routes if route.enabled]
    max_route_top_k = max((route.top_k for route in enabled_routes), default=30)
    final_top_k = 12 if route_decision.visual_result_mode == "gallery" else (
        10 if route_decision.answer_policy.must_return_visual else 8
    )
    return RetrievalSearchRequest(
        query=query,
        query_image_vector=query_image_vector,
        vector_top_k=min(max(max_route_top_k, 30), 100),
        full_text_top_k=min(max(max_route_top_k, 30), 100),
        top_k=final_top_k,
    )


def apply_route_preferences(
    items: Sequence[RetrievalResultItem],
    *,
    route_decision: RouteDecision,
) -> list[RetrievalResultItem]:
    contexts = list(items)
    if not route_decision.answer_policy.must_return_visual:
        return contexts
    return sorted(contexts, key=lambda item: item.modality != "image")


def apply_evidence_gate(
    items: Sequence[RetrievalResultItem],
    *,
    route_decision: RouteDecision,
) -> list[RetrievalResultItem]:
    limit = 12 if route_decision.visual_result_mode == "gallery" else 6
    contexts = list(items[:limit])
    if not contexts:
        return []
    threshold = get_settings().evidence_min_reranker_score
    if threshold is None:
        return contexts
    highest_score = max(item.score for item in contexts)
    if highest_score < threshold:
        return []
    return contexts


def apply_image_display_policy(
    items: Sequence[RetrievalResultItem],
    *,
    route_decision: RouteDecision,
) -> list[RetrievalResultItem]:
    sanitized_items: list[RetrievalResultItem] = []
    for item in items:
        sanitized_excerpt = sanitize_visible_text(item.excerpt)
        if not sanitized_excerpt:
            continue
        include_images = route_decision.search_image_vector
        modality = (
            item.modality
            if include_images
            else "text" if item.modality == "image" else item.modality
        )
        sanitized_items.append(
            item.model_copy(
                update={
                    "excerpt": sanitized_excerpt,
                    "modality": modality,
                    "image_url": item.image_url if include_images else None,
                    "image_urls": item.image_urls if include_images else [],
                    "image_alt": item.image_alt if include_images else None,
                }
            )
        )
    return sanitized_items


def expand_context_to_section_chunks(
    db: Session,
    *,
    knowledge_base_id: UUID,
    items: Sequence[RetrievalResultItem],
) -> list[RetrievalResultItem]:
    hit_item_by_id = parse_context_items_by_chunk_id(items)
    hit_ids = list(hit_item_by_id)
    if not hit_ids:
        return []

    hit_rows = db.execute(
        select(ChunkMetadata, File)
        .join(File, File.id == ChunkMetadata.file_id)
        .where(
            ChunkMetadata.id.in_(hit_ids),
            ChunkMetadata.knowledge_base_id == knowledge_base_id,
            ChunkMetadata.is_active.is_(True),
            File.deleted_at.is_(None),
            File.status == FileStatus.INDEXED.value,
        )
    ).all()
    hit_chunks_by_id: dict[UUID, tuple[ChunkMetadata, File]] = {
        chunk.id: (chunk, file) for chunk, file in hit_rows
    }
    if not hit_chunks_by_id:
        return []

    file_ids = {chunk.file_id for chunk, _file in hit_chunks_by_id.values()}
    file_chunk_rows = db.execute(
        select(ChunkMetadata, File)
        .join(File, File.id == ChunkMetadata.file_id)
        .where(
            ChunkMetadata.file_id.in_(file_ids),
            ChunkMetadata.knowledge_base_id == knowledge_base_id,
            ChunkMetadata.is_active.is_(True),
            File.deleted_at.is_(None),
            File.status == FileStatus.INDEXED.value,
        )
        .order_by(ChunkMetadata.file_id, ChunkMetadata.parse_job_id, ChunkMetadata.chunk_index)
    ).all()

    chunks_by_parse_job: dict[tuple[UUID, UUID], list[ChunkMetadata]] = {}
    files_by_id: dict[UUID, File] = {}
    for chunk, file in file_chunk_rows:
        chunks_by_parse_job.setdefault((chunk.file_id, chunk.parse_job_id), []).append(chunk)
        files_by_id[file.id] = file

    expanded_items: list[RetrievalResultItem] = []
    seen_chunk_ids: set[UUID] = set()
    for chunk_id in hit_ids:
        hit_pair = hit_chunks_by_id.get(chunk_id)
        hit_item = hit_item_by_id.get(chunk_id)
        if hit_pair is None or hit_item is None:
            continue
        hit_chunk, hit_file = hit_pair
        section_chunks = collect_section_chunks(
            chunks_by_parse_job.get((hit_chunk.file_id, hit_chunk.parse_job_id), []),
            hit_chunk=hit_chunk,
        )
        for section_chunk in section_chunks:
            if section_chunk.id in seen_chunk_ids:
                continue
            file = files_by_id.get(section_chunk.file_id, hit_file)
            expanded_items.append(
                RetrievalResultItem(
                    chunk_id=str(section_chunk.id),
                    file_id=str(file.id),
                    file_name=file.file_name,
                    source_locator=section_chunk.source_locator,
                    excerpt=build_display_chunk_text(section_chunk),
                    score=hit_item.score,
                    source=hit_item.source,
                    modality=infer_chunk_modality(section_chunk),
                    image_url=build_chunk_image_url(section_chunk),
                    image_urls=build_chunk_image_urls(section_chunk),
                    image_alt=build_chunk_image_alt(section_chunk, file),
                )
            )
            seen_chunk_ids.add(section_chunk.id)
    return expanded_items


def parse_context_items_by_chunk_id(
    items: Sequence[RetrievalResultItem],
) -> dict[UUID, RetrievalResultItem]:
    items_by_chunk_id: dict[UUID, RetrievalResultItem] = {}
    for item in items:
        try:
            chunk_id = UUID(item.chunk_id)
        except ValueError:
            continue
        if chunk_id in items_by_chunk_id:
            continue
        items_by_chunk_id[chunk_id] = item
    return items_by_chunk_id


def collect_section_chunks(
    chunks: Sequence[ChunkMetadata],
    *,
    hit_chunk: ChunkMetadata,
) -> list[ChunkMetadata]:
    if not hit_chunk.heading_path:
        return [hit_chunk]

    hit_index = next(
        (index for index, chunk in enumerate(chunks) if chunk.id == hit_chunk.id),
        None,
    )
    if hit_index is None:
        return [hit_chunk]

    start_index = hit_index
    while start_index > 0 and chunks[start_index - 1].heading_path == hit_chunk.heading_path:
        start_index -= 1

    end_index = hit_index
    while (
        end_index + 1 < len(chunks) and chunks[end_index + 1].heading_path == hit_chunk.heading_path
    ):
        end_index += 1

    return list(chunks[start_index : end_index + 1])


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
    rows = db.execute(
        select(MessageCitation, ChunkMetadata, File)
        .join(ChunkMetadata, ChunkMetadata.id == MessageCitation.chunk_id)
        .join(File, File.id == MessageCitation.file_id)
        .where(MessageCitation.message_id.in_(message_ids))
        .order_by(MessageCitation.citation_index)
    ).all()
    citations: dict[UUID, list[CitationResponse]] = {}
    for citation, chunk, file in rows:
        citations.setdefault(citation.message_id, []).append(
            build_citation_response(citation, chunk=chunk, file=file)
        )
    return citations


def load_attachments_for_messages(
    db: Session,
    message_ids: list[UUID],
) -> dict[UUID, list[MessageAttachmentResponse]]:
    if not message_ids:
        return {}
    rows = db.scalars(
        select(MessageAttachment)
        .where(MessageAttachment.message_id.in_(message_ids))
        .order_by(MessageAttachment.created_at)
    ).all()
    attachments: dict[UUID, list[MessageAttachmentResponse]] = {}
    for attachment in rows:
        attachments.setdefault(attachment.message_id, []).append(
            build_attachment_response(attachment)
        )
    return attachments


def build_attachment_responses(
    attachments: Sequence[MessageAttachment],
) -> list[MessageAttachmentResponse]:
    return [build_attachment_response(attachment) for attachment in attachments]


def build_attachment_response(attachment: MessageAttachment) -> MessageAttachmentResponse:
    return MessageAttachmentResponse(
        id=str(attachment.id),
        type=attachment.attachment_type,
        file_name=attachment.file_name,
        media_type=attachment.media_type,
        size_bytes=attachment.size_bytes,
        url=f"/api/v1/messages/{attachment.message_id}/attachments/{attachment.id}",
    )


def infer_message_visual_result_mode(citations: Sequence[CitationResponse]) -> str | None:
    image_count = sum(1 for citation in citations if citation.modality == "image")
    if image_count > 1:
        return "gallery"
    if image_count == 1:
        return "single"
    return None


def get_message_attachment_asset(
    db: Session,
    *,
    message_id: UUID,
    attachment_id: UUID,
    current_user: User,
    storage: ObjectStorage,
) -> tuple[bytes, str]:
    row = db.execute(
        select(MessageAttachment, Message, Conversation)
        .join(Message, Message.id == MessageAttachment.message_id)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(MessageAttachment.id == attachment_id, MessageAttachment.message_id == message_id)
    ).one_or_none()
    if row is None:
        raise ApiError(code="RESOURCE_NOT_FOUND", message="Attachment was not found.", status_code=404)
    attachment, _message, conversation = row
    if conversation.user_id != current_user.id or conversation.deleted_at is not None:
        raise ApiError(code="RESOURCE_NOT_FOUND", message="Attachment was not found.", status_code=404)
    return (
        storage.get_object(bucket=attachment.storage_bucket, key=attachment.storage_key),
        attachment.media_type,
    )


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
    attachments: list[MessageAttachmentResponse] | None = None,
    feedback_rating: str | None = None,
    visual_result_mode: str | None = None,
) -> MessageResponse:
    return MessageResponse(
        id=str(message.id),
        conversation_id=str(message.conversation_id),
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        citations=citations,
        attachments=attachments or [],
        feedback_rating=feedback_rating,
        visual_result_mode=visual_result_mode,
    )


def build_citation_response(
    citation: MessageCitation,
    *,
    context_item: RetrievalResultItem | None = None,
    chunk: ChunkMetadata | None = None,
    file: File | None = None,
    allow_images: bool | None = None,
) -> CitationResponse:
    should_include_images = (
        bool(getattr(citation, "allow_images", False)) if allow_images is None else allow_images
    )
    modality = context_item.modality if context_item else "text"
    image_url = context_item.image_url if context_item else None
    image_urls = context_item.image_urls if context_item else []
    image_alt = context_item.image_alt if context_item else None
    if chunk is not None:
        modality = infer_chunk_modality(chunk)
        if should_include_images:
            image_url = build_chunk_image_url(chunk)
            image_urls = build_chunk_image_urls(chunk)
            if file is not None:
                image_alt = build_chunk_image_alt(chunk, file)
        else:
            image_url = None
            image_urls = []
            image_alt = None
    if not should_include_images:
        modality = "text" if modality == "image" else modality
        image_url = None
        image_urls = []
        image_alt = None
    excerpt = sanitize_visible_text(citation.excerpt)
    return CitationResponse(
        id=str(citation.id),
        index=citation.citation_index,
        file_name=citation.source_label or "",
        source_locator=citation.source_locator,
        excerpt=excerpt,
        chunk_id=str(citation.chunk_id),
        modality=modality,
        image_url=image_url,
        image_urls=image_urls,
        image_alt=image_alt,
    )


def sanitize_visible_text(content: str) -> str:
    return normalize_special_elements(strip_visible_image_references(content))
