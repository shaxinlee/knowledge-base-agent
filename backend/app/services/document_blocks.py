import json
import re
import zipfile
from dataclasses import dataclass
from io import BytesIO
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models import DocumentBlock, File, FileStatus, ParseJob, ParseJobStatus
from app.schemas.files import ChunkDebugListResponse, ChunkDebugResponse
from app.services.object_storage import ObjectStorage

TEXT_EXTENSIONS = {".md", ".markdown"}
JSON_EXTENSIONS = {".json"}


@dataclass(frozen=True)
class NormalizedBlock:
    block_type: str
    content: str
    page_number: int | None
    slide_number: int | None
    sheet_name: str | None
    row_start: int | None
    row_end: int | None
    bbox: dict[str, Any] | None
    metadata: dict[str, Any]


def normalize_parse_job_result(
    db: Session,
    *,
    file: File,
    parse_job: ParseJob,
    storage: ObjectStorage,
) -> None:
    parsed_result = get_parsed_result_location(parse_job)
    if parsed_result is None:
        return

    result_bytes = storage.get_object(
        bucket=parsed_result["bucket"],
        key=parsed_result["key"],
    )
    normalized_blocks = extract_blocks_from_zip(result_bytes)
    if not normalized_blocks:
        parse_job.status = ParseJobStatus.FAILED.value
        parse_job.error_code = "PARSED_RESULT_EMPTY"
        parse_job.error_message = (
            "Parsed result did not contain supported Markdown or JSON content."
        )
        file.status = FileStatus.FAILED.value
        db.commit()
        return

    db.execute(delete(DocumentBlock).where(DocumentBlock.parse_job_id == parse_job.id))
    for block_index, normalized_block in enumerate(normalized_blocks):
        db.add(
            DocumentBlock(
                knowledge_base_id=file.knowledge_base_id,
                file_id=file.id,
                parse_job_id=parse_job.id,
                block_index=block_index,
                block_type=normalized_block.block_type,
                content=normalized_block.content,
                page_number=normalized_block.page_number,
                slide_number=normalized_block.slide_number,
                sheet_name=normalized_block.sheet_name,
                row_start=normalized_block.row_start,
                row_end=normalized_block.row_end,
                bbox=normalized_block.bbox,
                block_metadata=normalized_block.metadata,
            )
        )

    parse_job.status = ParseJobStatus.CHUNKING.value
    parse_job.progress = 50
    parse_job.logs = merge_normalization_logs(
        parse_job.logs,
        {
            "normalization": {
                "document_block_count": len(normalized_blocks),
                "source": "mineru_parsed_result_zip",
            }
        },
    )
    file.status = FileStatus.PROCESSING.value
    db.commit()


def list_block_debug_chunks(
    db: Session,
    *,
    file_id: UUID,
    page: int,
    page_size: int,
) -> ChunkDebugListResponse:
    normalized_page = max(page, 1)
    normalized_page_size = min(max(page_size, 1), 100)
    base_query = select(DocumentBlock).where(DocumentBlock.file_id == file_id)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    blocks = db.scalars(
        base_query.order_by(DocumentBlock.block_index)
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()

    return ChunkDebugListResponse(
        items=[build_block_debug_response(block) for block in blocks],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


def extract_blocks_from_zip(result_bytes: bytes) -> list[NormalizedBlock]:
    try:
        archive = zipfile.ZipFile(BytesIO(result_bytes))
    except zipfile.BadZipFile as exc:
        raise ApiError(
            code="VALIDATION_ERROR",
            message="Parsed result is not a valid zip archive.",
            status_code=400,
        ) from exc

    blocks: list[NormalizedBlock] = []
    for name in sorted(archive.namelist()):
        suffix = get_suffix(name)
        if suffix in TEXT_EXTENSIONS:
            blocks.extend(parse_markdown_blocks(archive.read(name), source_name=name))
        elif suffix in JSON_EXTENSIONS:
            blocks.extend(parse_json_blocks(archive.read(name), source_name=name))
    return blocks


def parse_markdown_blocks(content: bytes, *, source_name: str) -> list[NormalizedBlock]:
    text = content.decode("utf-8", errors="ignore")
    blocks: list[NormalizedBlock] = []
    heading_path: list[str] = []
    for paragraph in split_markdown(text):
        heading = parse_markdown_heading(paragraph)
        if heading is not None:
            level, title = heading
            heading_path = update_heading_path(heading_path, level=level, title=title)
            block_type = "heading"
            metadata = {
                "source_name": source_name,
                "source_format": "markdown",
                "heading_level": level,
                "heading_path": heading_path.copy(),
            }
        else:
            block_type = "table" if is_markdown_table(paragraph) else "text"
            metadata = {
                "source_name": source_name,
                "source_format": "markdown",
                "heading_path": heading_path.copy() if heading_path else None,
            }
        blocks.append(
            NormalizedBlock(
                block_type=block_type,
                content=paragraph,
                page_number=None,
                slide_number=None,
                sheet_name=None,
                row_start=None,
                row_end=None,
                bbox=None,
                metadata=metadata,
            )
        )
    return blocks


def parse_json_blocks(content: bytes, *, source_name: str) -> list[NormalizedBlock]:
    try:
        payload = json.loads(content.decode("utf-8", errors="ignore"))
    except json.JSONDecodeError:
        return []

    blocks: list[NormalizedBlock] = []
    for candidate in find_json_block_candidates(payload):
        text = get_candidate_text(candidate)
        if not text:
            continue
        block_type = normalize_json_block_type(candidate)
        heading_path = get_heading_path(candidate)
        source_locator = get_candidate_source_locator(candidate)
        raw_keys = sorted(str(key) for key in candidate.keys())
        metadata: dict[str, Any] = {
            "source_name": source_name,
            "source_format": "json",
            "raw_keys": raw_keys,
        }
        if heading_path:
            metadata["heading_path"] = heading_path
        if source_locator:
            metadata["source_locator"] = source_locator
        asset_path = get_str(
            candidate.get("asset_path")
            or candidate.get("image_path")
            or candidate.get("img_path")
            or candidate.get("path")
        )
        if asset_path:
            metadata["asset_path"] = asset_path
        blocks.append(
            NormalizedBlock(
                block_type=block_type,
                content=text,
                page_number=get_page_number(candidate),
                slide_number=get_int(candidate.get("slide_number") or candidate.get("slide")),
                sheet_name=get_str(candidate.get("sheet_name") or candidate.get("sheet")),
                row_start=get_int(candidate.get("row_start")),
                row_end=get_int(candidate.get("row_end")),
                bbox=get_dict(candidate.get("bbox")),
                metadata=metadata,
            )
        )
    return blocks


def find_json_block_candidates(
    payload: Any, inherited_context: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    context = inherited_context or {}
    if isinstance(payload, dict):
        next_context = merge_json_context(context, payload)
        candidates: list[dict[str, Any]] = []
        if get_candidate_text(payload):
            candidate = dict(next_context)
            candidate.update(payload)
            candidates.append(candidate)
        for key in (
            "blocks",
            "document_blocks",
            "pages",
            "content",
            "children",
            "items",
            "layout_dets",
            "para_blocks",
            "tables",
            "images",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                candidates.extend(find_json_block_candidates(value, next_context))
        for value in payload.values():
            if isinstance(value, dict):
                candidates.extend(find_json_block_candidates(value, next_context))
        return candidates
    if isinstance(payload, list):
        candidates = []
        for item in payload:
            candidates.extend(find_json_block_candidates(item, context))
        return candidates
    return []


def get_candidate_text(candidate: dict[str, Any]) -> str:
    for key in ("content", "text", "md", "markdown", "html"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    table_body = candidate.get("table_body")
    if isinstance(table_body, str) and table_body.strip():
        return table_body.strip()
    lines = candidate.get("lines")
    if isinstance(lines, list):
        line_texts = [get_candidate_text(line) for line in lines if isinstance(line, dict)]
        joined = "\n".join(text for text in line_texts if text)
        if joined.strip():
            return joined.strip()
    return ""


def split_markdown(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]


def get_parsed_result_location(parse_job: ParseJob) -> dict[str, str] | None:
    logs = parse_job.logs or {}
    parsed_result = logs.get("parsed_result")
    if not isinstance(parsed_result, dict):
        return None
    bucket = parsed_result.get("bucket")
    key = parsed_result.get("key")
    if not isinstance(bucket, str) or not isinstance(key, str):
        return None
    return {"bucket": bucket, "key": key}


def build_block_debug_response(block: DocumentBlock) -> ChunkDebugResponse:
    content = block.content or ""
    return ChunkDebugResponse(
        id=str(block.id),
        file_id=str(block.file_id),
        knowledge_base_id=str(block.knowledge_base_id),
        content=content,
        source_locator=build_source_locator(block),
        token_count=count_tokens(content),
        is_active=True,
        created_at=block.created_at,
    )


def build_source_locator(block: DocumentBlock) -> str:
    metadata = block.block_metadata or {}
    source_name = str(metadata.get("source_name") or "document")
    if block.page_number is not None:
        return f"pdf:p{block.page_number}"
    if block.slide_number is not None:
        return f"pptx:slide-{block.slide_number}"
    if block.sheet_name:
        row_range = ""
        if block.row_start is not None and block.row_end is not None:
            row_range = f"!row-{block.row_start}-row-{block.row_end}"
        return f"xlsx:{block.sheet_name}{row_range}"
    return f"block:{source_name}#{block.block_index + 1}"


def merge_normalization_logs(
    existing_logs: dict[str, Any] | None, new_logs: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(existing_logs or {})
    merged.update(new_logs)
    return merged


def get_suffix(name: str) -> str:
    lowered = name.lower()
    for suffix in (*TEXT_EXTENSIONS, *JSON_EXTENSIONS):
        if lowered.endswith(suffix):
            return suffix
    return ""


def parse_markdown_heading(content: str) -> tuple[int, str] | None:
    first_line = content.splitlines()[0] if content.splitlines() else ""
    match = re.match(r"^(#{1,6})\s+(.+?)\s*$", first_line.strip())
    if match is None:
        return None
    return len(match.group(1)), match.group(2).strip()


def update_heading_path(existing_path: list[str], *, level: int, title: str) -> list[str]:
    next_path = existing_path[: max(level - 1, 0)]
    next_path.append(title)
    return next_path


def is_markdown_table(content: str) -> bool:
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    if not all("|" in line for line in lines[:2]):
        return False
    separator = lines[1].replace("|", "").replace(":", "").replace("-", "").strip()
    return separator == ""


def merge_json_context(context: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    next_context = dict(context)
    page_number = get_page_number(payload)
    if page_number is not None:
        next_context["page_number"] = page_number
    slide_number = get_int(payload.get("slide_number") or payload.get("slide"))
    if slide_number is not None:
        next_context["slide_number"] = slide_number
    sheet_name = get_str(payload.get("sheet_name") or payload.get("sheet"))
    if sheet_name:
        next_context["sheet_name"] = sheet_name
    for key in ("row_start", "row_end", "bbox"):
        value = payload.get(key)
        if value is not None:
            next_context[key] = value
    heading_path = get_heading_path(payload)
    if heading_path:
        next_context["heading_path"] = heading_path
    return next_context


def normalize_json_block_type(candidate: dict[str, Any]) -> str:
    raw_type = str(
        candidate.get("type")
        or candidate.get("block_type")
        or candidate.get("category")
        or candidate.get("kind")
        or "text"
    ).lower()
    if "title" in raw_type or "heading" in raw_type:
        return "heading"
    if "table" in raw_type:
        return "table"
    if "image" in raw_type or "figure" in raw_type or "ocr" in raw_type:
        return "image_ocr"
    return raw_type.replace("-", "_")


def get_page_number(candidate: dict[str, Any]) -> int | None:
    for key in ("page_number", "page_no", "page"):
        value = get_int(candidate.get(key))
        if value is not None:
            return value
    page_idx = get_int(candidate.get("page_idx"))
    if page_idx is not None:
        return page_idx + 1
    return None


def get_heading_path(candidate: dict[str, Any]) -> list[str] | None:
    value = (
        candidate.get("heading_path")
        or candidate.get("title_path")
        or candidate.get("section_path")
        or candidate.get("hierarchy")
    )
    if isinstance(value, list):
        path = [str(item).strip() for item in value if str(item).strip()]
        return path or None
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in re.split(r">\s*|/", value) if part.strip()]
    return None


def get_candidate_source_locator(candidate: dict[str, Any]) -> str | None:
    for key in ("source_locator", "locator"):
        value = candidate.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    region = get_int(candidate.get("ocr_region") or candidate.get("region_index"))
    if region is not None:
        return f"image:ocr-region-{region}"
    return None


def get_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def get_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def get_dict(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def count_tokens(content: str) -> int:
    return len(content.split())
