import re
from typing import Any
from urllib.parse import quote

from app.models import ChunkMetadata, File

IMAGE_SOURCE_TYPES = {"image", "jpg", "jpeg", "png", "webp", "gif", "bmp"}
VISIBLE_IMAGE_REFERENCE_PATTERN = re.compile(
    r"(?i)(?:"
    r"https?://\S+\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?\S*)?"
    r"|/api/v1/files/\S+"
    r"|(?:[\w.-]+/)*images/[^\s)\]]+\.(?:jpg|jpeg|png|webp|gif|bmp)(?:\?\S*)?"
    r")"
)


def infer_chunk_modality(chunk: ChunkMetadata) -> str:
    return "image" if chunk_has_image_source(chunk) else "text"


def build_chunk_image_url(chunk: ChunkMetadata) -> str | None:
    image_urls = build_chunk_image_urls(chunk)
    return image_urls[0] if image_urls else None


def build_chunk_image_urls(chunk: ChunkMetadata) -> list[str]:
    asset_paths = get_asset_paths(chunk)
    if asset_paths:
        return [build_asset_url(chunk, asset_path) for asset_path in asset_paths]
    if chunk.source_type.lower() in IMAGE_SOURCE_TYPES:
        return [f"/api/v1/files/{chunk.file_id}/raw"]
    return []


def build_chunk_image_alt(chunk: ChunkMetadata, file: File) -> str | None:
    if not chunk_has_image_source(chunk):
        return None
    if chunk.description and chunk.description.strip():
        return " ".join(chunk.description.split())[:160]
    excerpt = " ".join(strip_visible_image_references(chunk.content).split())
    if excerpt:
        return excerpt[:160]
    return f"{file.file_name} {chunk.source_locator}".strip()


def chunk_has_image_source(chunk: ChunkMetadata) -> bool:
    source_type = chunk.source_type.lower()
    if source_type in IMAGE_SOURCE_TYPES:
        return True
    if chunk.source_locator.lower().startswith("image:"):
        return True
    metadata = chunk.chunk_metadata or {}
    block_types = metadata.get("document_block_types")
    if isinstance(block_types, list) and any("image" in str(item) for item in block_types):
        return True
    return bool(get_asset_paths(chunk))


def get_first_asset_path(chunk: ChunkMetadata) -> str | None:
    asset_paths = get_asset_paths(chunk)
    return asset_paths[0] if asset_paths else None


def get_asset_paths(chunk: ChunkMetadata) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    metadata = chunk.chunk_metadata or {}
    for key in ("asset_path", "image_path", "img_path"):
        value = metadata.get(key)
        if isinstance(value, str):
            append_asset_path(paths, seen, value)
    asset_paths = metadata.get("asset_paths")
    if isinstance(asset_paths, list):
        for value in asset_paths:
            if isinstance(value, str):
                append_asset_path(paths, seen, value)
    for value in extract_markdown_image_paths(chunk.content):
        append_asset_path(paths, seen, value)
    return paths


def extract_asset_paths_from_metadata(metadata_items: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for metadata in metadata_items:
        for key in ("asset_path", "image_path", "img_path"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip() and value.strip() not in seen:
                paths.append(value.strip())
                seen.add(value.strip())
    return paths


def extract_markdown_image_paths(content: str) -> list[str]:
    paths: list[str] = []
    for match in re.finditer(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", content):
        paths.append(match.group(1))
    lines = [line.strip() for line in content.splitlines()]
    for index, line in enumerate(lines[:-1]):
        if re.fullmatch(r"!\[[^\]]*\]", line):
            next_line = lines[index + 1]
            if next_line.startswith("(") and next_line.endswith(")"):
                paths.append(next_line[1:-1].strip())
    return [path for path in paths if looks_like_image_path(path)]


def strip_markdown_image_references(content: str) -> str:
    stripped = re.sub(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", "", content)
    lines = stripped.splitlines()
    cleaned_lines: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if re.fullmatch(r"!\[[^\]]*\]", line):
            if next_line.startswith("(") and next_line.endswith(")"):
                path = next_line[1:-1].strip()
                if looks_like_image_path(path):
                    index += 2
                    continue
            index += 1
            continue
        if line.startswith("(") and line.endswith(")") and looks_like_image_path(line[1:-1]):
            index += 1
            continue
        if looks_like_image_path(line):
            index += 1
            continue
        cleaned_lines.append(lines[index])
        index += 1
    return "\n".join(cleaned_lines).strip()


def strip_visible_image_references(content: str) -> str:
    stripped = strip_markdown_image_references(content)
    stripped = VISIBLE_IMAGE_REFERENCE_PATTERN.sub("", stripped)
    return "\n".join(line.rstrip() for line in stripped.splitlines()).strip()


def looks_like_image_path(value: str) -> bool:
    lowered = value.lower().split("?", 1)[0]
    return lowered.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"))


def append_asset_path(paths: list[str], seen: set[str], value: str) -> None:
    normalized = value.strip()
    if normalized and normalized not in seen:
        paths.append(normalized)
        seen.add(normalized)


def build_asset_url(chunk: ChunkMetadata, asset_path: str) -> str:
    if is_direct_image_url(asset_path):
        return asset_path
    return f"/api/v1/files/{chunk.file_id}/assets?path={quote(asset_path, safe='')}"


def is_direct_image_url(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered.startswith("http://")
        or lowered.startswith("https://")
        or lowered.startswith("data:image/")
    )
