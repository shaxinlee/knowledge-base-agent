import base64
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.models import ChunkMetadata, File, ParseJob
from app.services.file_assets import FileAsset, get_parsed_file_asset, get_raw_file_asset
from app.services.llm import (
    build_chat_completions_url,
    build_llm_headers,
    parse_chat_completion_content,
)
from app.services.model_settings import get_model_settings
from app.services.object_storage import ObjectStorage
from app.services.visual_citations import get_asset_paths

IMAGE_DESCRIPTION_PROMPT = (
    "请用中文为这张文档图片生成便于知识库检索的简洁描述。"
    "描述图片主体、可见文字、结构关系、图表趋势、页面元素和可能的业务含义；"
    "如果信息不可见，请明确说不可见，不要编造。"
)
MAX_IMAGES_PER_CHUNK = 3


@dataclass(frozen=True)
class ImageDescriptionInput:
    image_bytes: bytes
    media_type: str
    context_text: str
    source_locator: str
    file_name: str


class ImageDescriptionClientProtocol(Protocol):
    enabled: bool
    model: str

    def describe_image(self, image: ImageDescriptionInput) -> str:
        pass


class DisabledImageDescriptionClient:
    enabled = False
    model = ""

    def describe_image(self, image: ImageDescriptionInput) -> str:
        raise ApiError(
            code="IMAGE_DESCRIPTION_DISABLED",
            message="Image description is not configured.",
            status_code=503,
            details={},
        )


class OpenAIVisionImageDescriptionClient:
    enabled = True

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 120,
        temperature: float = 0.2,
        max_tokens: int = 800,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.transport = transport

    def describe_image(self, image: ImageDescriptionInput) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": build_image_description_prompt(image),
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": build_data_url(
                                    media_type=image.media_type,
                                    image_bytes=image.image_bytes,
                                )
                            },
                        },
                    ],
                }
            ],
            "stream": False,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    build_chat_completions_url(self.base_url),
                    headers=build_llm_headers(self.api_key),
                    json=payload,
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError(
                code="UPSTREAM_SERVICE_ERROR",
                message="Image description API request failed.",
                status_code=502,
                details={"service": "image-description-api", "error": str(exc)},
            ) from exc

        return parse_chat_completion_content(response.json())


def enrich_image_chunk_descriptions(
    db: Session,
    *,
    file: File,
    parse_job: ParseJob,
    storage: ObjectStorage,
    image_description_client: ImageDescriptionClientProtocol,
) -> None:
    chunks = db.scalars(
        select(ChunkMetadata)
        .where(
            ChunkMetadata.parse_job_id == parse_job.id,
            ChunkMetadata.file_id == file.id,
            ChunkMetadata.is_active.is_(True),
        )
        .order_by(ChunkMetadata.chunk_index)
    ).all()
    image_chunks = [chunk for chunk in chunks if is_image_chunk(chunk)]
    if not image_chunks:
        return

    warnings: list[dict[str, Any]] = []
    generated_count = 0
    skipped_count = 0
    failed_count = 0
    for chunk in image_chunks:
        if not image_description_client.enabled:
            skipped_count += 1
            mark_description_metadata(
                chunk,
                status="skipped",
                model=image_description_client.model,
            )
            continue

        try:
            image_assets = load_chunk_image_assets(
                db,
                file=file,
                chunk=chunk,
                storage=storage,
            )
        except ApiError as exc:
            failed_count += 1
            warnings.append(build_description_warning(chunk=chunk, message=exc.message))
            mark_description_metadata(
                chunk,
                status="failed",
                model=image_description_client.model,
                error=exc.message,
            )
            continue

        if not image_assets:
            skipped_count += 1
            mark_description_metadata(
                chunk,
                status="skipped",
                model=image_description_client.model,
            )
            continue

        descriptions: list[str] = []
        for asset in image_assets[:MAX_IMAGES_PER_CHUNK]:
            try:
                description = image_description_client.describe_image(
                    ImageDescriptionInput(
                        image_bytes=asset.content,
                        media_type=asset.media_type,
                        context_text=chunk.content,
                        source_locator=chunk.source_locator,
                        file_name=file.file_name,
                    )
                )
            except ApiError as exc:
                failed_count += 1
                warnings.append(build_description_warning(chunk=chunk, message=exc.message))
                mark_description_metadata(
                    chunk,
                    status="failed",
                    model=image_description_client.model,
                    error=exc.message,
                )
                descriptions = []
                break
            descriptions.append(description)

        if not descriptions:
            continue
        chunk.description = merge_image_descriptions(descriptions)
        generated_count += 1
        mark_description_metadata(
            chunk,
            status="generated",
            model=image_description_client.model,
        )

    parse_job.logs = merge_image_description_logs(
        parse_job.logs,
        {
            "image_description": {
                "model": image_description_client.model,
                "image_chunk_count": len(image_chunks),
                "generated_count": generated_count,
                "skipped_count": skipped_count,
                "failed_count": failed_count,
                "warnings": warnings[:20],
            }
        },
    )
    db.commit()


def is_image_chunk(chunk: ChunkMetadata) -> bool:
    metadata = chunk.chunk_metadata or {}
    block_types = metadata.get("document_block_types")
    if isinstance(block_types, list) and any("image" in str(item) for item in block_types):
        return True
    if get_asset_paths(chunk):
        return True
    if chunk.source_locator.lower().startswith("image:"):
        return True
    return chunk.source_type.lower() in {"image", "jpg", "jpeg", "png", "webp", "gif", "bmp"}


def load_chunk_image_assets(
    db: Session,
    *,
    file: File,
    chunk: ChunkMetadata,
    storage: ObjectStorage,
) -> list[FileAsset]:
    asset_paths = get_asset_paths(chunk)
    if asset_paths:
        assets = []
        for asset_path in asset_paths[:MAX_IMAGES_PER_CHUNK]:
            if asset_path.startswith(("http://", "https://", "data:image/")):
                continue
            assets.append(
                get_parsed_file_asset(
                    db,
                    file_id=file.id,
                    asset_path=asset_path,
                    storage=storage,
                )
            )
        return assets
    if chunk.source_type.lower() in {"image", "jpg", "jpeg", "png", "webp", "gif", "bmp"}:
        return [get_raw_file_asset(db, file_id=file.id, storage=storage)]
    return []


def mark_description_metadata(
    chunk: ChunkMetadata,
    *,
    status: str,
    model: str,
    error: str | None = None,
) -> None:
    metadata = dict(chunk.chunk_metadata or {})
    metadata["description_status"] = status
    metadata["description_model"] = model or None
    if error:
        metadata["description_error"] = error[:500]
    else:
        metadata.pop("description_error", None)
    chunk.chunk_metadata = metadata


def build_image_description_prompt(image: ImageDescriptionInput) -> str:
    context = " ".join(image.context_text.split())
    parts = [
        IMAGE_DESCRIPTION_PROMPT,
        f"文件名：{image.file_name}",
        f"位置：{image.source_locator}",
    ]
    if context:
        parts.append(f"OCR 或相邻文本：{context[:1200]}")
    return "\n".join(parts)


def build_data_url(*, media_type: str, image_bytes: bytes) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


def merge_image_descriptions(descriptions: Sequence[str]) -> str:
    cleaned = [description.strip() for description in descriptions if description.strip()]
    if len(cleaned) <= 1:
        return cleaned[0] if cleaned else ""
    return "\n\n".join(
        f"图片 {index}: {description}" for index, description in enumerate(cleaned, start=1)
    )


def build_description_warning(*, chunk: ChunkMetadata, message: str) -> dict[str, Any]:
    return {
        "chunk_id": str(chunk.id),
        "chunk_index": chunk.chunk_index,
        "source_locator": chunk.source_locator,
        "message": message,
    }


def merge_image_description_logs(
    existing_logs: dict[str, Any] | None, new_logs: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(existing_logs or {})
    merged.update(new_logs)
    return merged


def get_image_description_client() -> ImageDescriptionClientProtocol:
    settings = get_settings()
    model_settings = get_model_settings()
    image_settings = model_settings.image_description
    llm_settings = model_settings.llm
    if not settings.image_description_enabled:
        return DisabledImageDescriptionClient()
    base_url = (
        image_settings.base_url.strip()
        or llm_settings.base_url.strip()
        or settings.image_description_api_base_url.strip()
        or settings.llm_api_base_url.strip()
        or settings.llm_api_base.strip()
    )
    model = image_settings.model.strip() or settings.image_description_model.strip()
    if not base_url or not model:
        return DisabledImageDescriptionClient()
    api_key = (
        image_settings.api_key
        or llm_settings.api_key
        or settings.image_description_api_key
        or settings.llm_api_key
    )
    return OpenAIVisionImageDescriptionClient(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_seconds=settings.image_description_timeout_seconds,
        temperature=settings.image_description_temperature,
        max_tokens=settings.image_description_max_tokens,
    )
