import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import ChunkMetadata, DocumentBlock, File, FileStatus, ParseJob, ParseJobStatus
from app.schemas.files import ChunkDebugListResponse, ChunkDebugResponse

TARGET_CHUNK_CHARS = 1000
MAX_CHUNK_CHARS = 1200
CHUNK_OVERLAP_CHARS = 120


@dataclass
class ChunkDraft:
    content: str
    source_blocks: list[DocumentBlock]
    heading_path: list[str] | None
    source_locator: str
    metadata: dict[str, Any]


def generate_chunks_for_parse_job(db: Session, *, file: File, parse_job: ParseJob) -> None:
    blocks = db.scalars(
        select(DocumentBlock)
        .where(DocumentBlock.parse_job_id == parse_job.id)
        .order_by(DocumentBlock.block_index)
    ).all()
    if not blocks:
        parse_job.status = ParseJobStatus.FAILED.value
        parse_job.error_code = "NO_DOCUMENT_BLOCKS"
        parse_job.error_message = "No document blocks were found for chunking."
        file.status = FileStatus.FAILED.value
        db.commit()
        return

    db.execute(
        update(ChunkMetadata)
        .where(ChunkMetadata.file_id == file.id, ChunkMetadata.is_active.is_(True))
        .values(is_active=False)
    )

    chunk_drafts = build_chunk_drafts(blocks=blocks, file=file)
    for chunk_count, chunk_draft in enumerate(chunk_drafts):
        first_block = chunk_draft.source_blocks[0]
        page_numbers = [
            block.page_number
            for block in chunk_draft.source_blocks
            if block.page_number is not None
        ]
        db.add(
            ChunkMetadata(
                knowledge_base_id=file.knowledge_base_id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                chunk_index=chunk_count,
                content=chunk_draft.content,
                content_hash=hash_content(chunk_draft.content),
                token_count=count_tokens(chunk_draft.content),
                page_start=min(page_numbers) if page_numbers else first_block.page_number,
                page_end=max(page_numbers) if page_numbers else first_block.page_number,
                slide_number=first_block.slide_number,
                sheet_name=first_block.sheet_name,
                row_start=first_block.row_start,
                row_end=chunk_draft.source_blocks[-1].row_end or first_block.row_end,
                heading_path=chunk_draft.heading_path,
                source_type=build_source_type(file),
                source_locator=chunk_draft.source_locator,
                chunk_metadata=chunk_draft.metadata,
                is_active=True,
            )
        )

    if not chunk_drafts:
        parse_job.status = ParseJobStatus.FAILED.value
        parse_job.error_code = "NO_CHUNK_CONTENT"
        parse_job.error_message = "Document blocks did not contain chunkable content."
        file.status = FileStatus.FAILED.value
        db.commit()
        return

    parse_job.status = ParseJobStatus.EMBEDDING.value
    parse_job.progress = 60
    parse_job.logs = merge_chunking_logs(
        parse_job.logs,
        {
            "chunking": {
                "chunk_count": len(chunk_drafts),
                "strategy": "heading_aware_recursive",
                "target_chars": TARGET_CHUNK_CHARS,
                "max_chars": MAX_CHUNK_CHARS,
                "overlap_chars": CHUNK_OVERLAP_CHARS,
            }
        },
    )
    file.status = FileStatus.PROCESSING.value
    db.commit()


def build_chunk_drafts(*, blocks: Sequence[DocumentBlock], file: File) -> list[ChunkDraft]:
    drafts: list[ChunkDraft] = []
    buffer_blocks: list[DocumentBlock] = []
    buffer_parts: list[str] = []
    buffer_heading_path: list[str] | None = None

    def flush_buffer() -> None:
        nonlocal buffer_blocks, buffer_parts, buffer_heading_path
        if not buffer_parts or not buffer_blocks:
            buffer_blocks = []
            buffer_parts = []
            buffer_heading_path = None
            return
        content = "\n\n".join(buffer_parts).strip()
        drafts.extend(
            split_blocks_into_drafts(
                content=content,
                source_blocks=buffer_blocks,
                heading_path=buffer_heading_path,
                file=file,
                split_reason="merged_text_blocks",
            )
        )
        buffer_blocks = []
        buffer_parts = []
        buffer_heading_path = None

    for block in blocks:
        content = (block.content or "").strip()
        if not content:
            continue
        block_type = normalize_block_type(block.block_type)
        heading_path = get_block_heading_path(block)
        if block_type in {"table", "image_ocr"}:
            flush_buffer()
            drafts.extend(
                split_blocks_into_drafts(
                    content=content,
                    source_blocks=[block],
                    heading_path=heading_path,
                    file=file,
                    split_reason=block_type,
                    keep_boundary=True,
                )
            )
            continue
        if block_type == "heading":
            if buffer_parts:
                flush_buffer()
            buffer_blocks.append(block)
            buffer_parts.append(content)
            buffer_heading_path = heading_path or [normalize_heading(content)]
            continue
        if buffer_parts and (
            buffer_heading_path != heading_path
            or len("\n\n".join([*buffer_parts, content])) > TARGET_CHUNK_CHARS
        ):
            flush_buffer()
        buffer_blocks.append(block)
        buffer_parts.append(content)
        buffer_heading_path = heading_path

    flush_buffer()
    return drafts


def split_blocks_into_drafts(
    *,
    content: str,
    source_blocks: list[DocumentBlock],
    heading_path: list[str] | None,
    file: File,
    split_reason: str,
    keep_boundary: bool = False,
) -> list[ChunkDraft]:
    first_block = source_blocks[0]
    chunks = split_text_recursively(content, keep_boundary=keep_boundary)
    drafts: list[ChunkDraft] = []
    for part_index, chunk_content in enumerate(chunks):
        source_locator = build_chunk_source_locator(
            blocks=source_blocks,
            file=file,
            heading_path=heading_path,
            part_index=part_index if len(chunks) > 1 else None,
        )
        drafts.append(
            ChunkDraft(
                content=chunk_content,
                source_blocks=source_blocks,
                heading_path=heading_path.copy() if heading_path else None,
                source_locator=source_locator,
                metadata={
                    "document_block_ids": [str(block.id) for block in source_blocks],
                    "document_block_indexes": [block.block_index for block in source_blocks],
                    "document_block_types": [
                        normalize_block_type(block.block_type) for block in source_blocks
                    ],
                    "split_reason": split_reason,
                    "split_part_index": part_index,
                    "split_part_count": len(chunks),
                    "source_name": (first_block.block_metadata or {}).get("source_name"),
                },
            )
        )
    return drafts


def split_text_recursively(content: str, *, keep_boundary: bool = False) -> list[str]:
    cleaned = content.strip()
    if not cleaned:
        return []
    if len(cleaned) <= MAX_CHUNK_CHARS:
        return [cleaned]

    separators = ["\n\n", "\n", "。", ".", " "]
    for separator in separators:
        parts = [part.strip() for part in cleaned.split(separator) if part.strip()]
        if len(parts) <= 1:
            continue
        chunks = merge_split_parts(parts, separator=separator)
        if chunks:
            return chunks

    if keep_boundary:
        return [cleaned]
    return sliding_window_split(cleaned)


def merge_split_parts(parts: list[str], *, separator: str) -> list[str]:
    chunks: list[str] = []
    current = ""
    joiner = separator if separator in {"\n\n", "\n", " "} else f"{separator} "
    for part in parts:
        candidate = part if not current else f"{current}{joiner}{part}"
        if len(candidate) <= MAX_CHUNK_CHARS:
            current = candidate
            continue
        if current:
            chunks.append(current.strip())
        if len(part) > MAX_CHUNK_CHARS:
            chunks.extend(sliding_window_split(part))
            current = ""
        else:
            current = part
    if current:
        chunks.append(current.strip())
    return add_overlap(chunks)


def sliding_window_split(content: str) -> list[str]:
    chunks: list[str] = []
    start = 0
    while start < len(content):
        end = min(start + MAX_CHUNK_CHARS, len(content))
        chunks.append(content[start:end].strip())
        if end == len(content):
            break
        start = max(end - CHUNK_OVERLAP_CHARS, start + 1)
    return chunks


def add_overlap(chunks: list[str]) -> list[str]:
    if len(chunks) <= 1:
        return chunks
    overlapped = [chunks[0]]
    for previous, current in zip(chunks, chunks[1:]):
        overlap = previous[-CHUNK_OVERLAP_CHARS:].strip()
        overlapped.append(f"{overlap}\n\n{current}".strip() if overlap else current)
    return overlapped


def list_chunks(
    db: Session,
    *,
    file_id: UUID,
    page: int,
    page_size: int,
) -> ChunkDebugListResponse:
    normalized_page = max(page, 1)
    normalized_page_size = min(max(page_size, 1), 100)
    base_query = select(ChunkMetadata).where(
        ChunkMetadata.file_id == file_id,
        ChunkMetadata.is_active.is_(True),
    )
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    chunks = db.scalars(
        base_query.order_by(ChunkMetadata.chunk_index)
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()
    return ChunkDebugListResponse(
        items=[build_chunk_response(chunk) for chunk in chunks],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


def build_chunk_response(chunk: ChunkMetadata) -> ChunkDebugResponse:
    return ChunkDebugResponse(
        id=str(chunk.id),
        file_id=str(chunk.file_id),
        knowledge_base_id=str(chunk.knowledge_base_id),
        content=chunk.content,
        source_locator=chunk.source_locator,
        token_count=chunk.token_count or 0,
        is_active=chunk.is_active,
        created_at=chunk.created_at,
    )


def build_source_type(file: File) -> str:
    extension = file.file_ext.lstrip(".").lower()
    if extension in {"jpg", "jpeg", "png", "webp"}:
        return "image"
    return extension or "txt"


def build_chunk_source_locator(
    *,
    blocks: list[DocumentBlock],
    file: File,
    heading_path: list[str] | None,
    part_index: int | None,
) -> str:
    first_block = blocks[0]
    metadata_locator = get_metadata_source_locator(first_block)
    if metadata_locator:
        return append_part_locator(metadata_locator, part_index)

    source_type = build_source_type(file)
    page_numbers = [block.page_number for block in blocks if block.page_number is not None]
    if page_numbers:
        page_start = min(page_numbers)
        page_end = max(page_numbers)
        page_locator = f"{source_type}:p{page_start}"
        if page_end != page_start:
            page_locator = f"{source_type}:p{page_start}-p{page_end}"
        return append_part_locator(page_locator, part_index)
    if first_block.slide_number is not None:
        return append_part_locator(f"{source_type}:slide-{first_block.slide_number}", part_index)
    if first_block.sheet_name:
        row_range = ""
        row_start = first_block.row_start
        row_end = blocks[-1].row_end or first_block.row_end
        if row_start is not None and row_end is not None:
            row_range = f"!row-{row_start}-row-{row_end}"
        return append_part_locator(f"{source_type}:{first_block.sheet_name}{row_range}", part_index)
    if source_type in {"md", "markdown", "docx"} and heading_path:
        return append_part_locator(f"{source_type}:{' > '.join(heading_path)}", part_index)
    if source_type == "image":
        region = get_image_region(first_block)
        if region is not None:
            return append_part_locator(f"image:ocr-region-{region}", part_index)
    return append_part_locator(f"{source_type}:block-{first_block.block_index + 1}", part_index)


def hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def count_tokens(content: str) -> int:
    return len(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]|[^\s]", content))


def normalize_heading(content: str) -> str:
    return content.lstrip("#").strip()


def normalize_block_type(block_type: str | None) -> str:
    normalized = (block_type or "text").lower().replace("-", "_")
    if "table" in normalized:
        return "table"
    if "image" in normalized or "ocr" in normalized or "figure" in normalized:
        return "image_ocr"
    if "heading" in normalized or "title" in normalized:
        return "heading"
    return normalized


def get_block_heading_path(block: DocumentBlock) -> list[str] | None:
    metadata = block.block_metadata or {}
    value = metadata.get("heading_path")
    if isinstance(value, list):
        path = [str(item).strip() for item in value if str(item).strip()]
        return path or None
    if normalize_block_type(block.block_type) == "heading":
        return [normalize_heading(block.content or "")]
    return None


def get_metadata_source_locator(block: DocumentBlock) -> str | None:
    metadata = block.block_metadata or {}
    value = metadata.get("source_locator")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def get_image_region(block: DocumentBlock) -> int | None:
    metadata = block.block_metadata or {}
    value = metadata.get("ocr_region") or metadata.get("region_index")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def append_part_locator(locator: str, part_index: int | None) -> str:
    if part_index is None:
        return locator
    return f"{locator}#part-{part_index + 1}"


def merge_chunking_logs(
    existing_logs: dict[str, Any] | None, new_logs: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(existing_logs or {})
    merged.update(new_logs)
    return merged
