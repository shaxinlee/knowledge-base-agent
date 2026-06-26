from app.models import ChunkMetadata
from app.services.visual_citations import chunk_has_image_source, strip_visible_image_references


def build_indexable_chunk_text(chunk: ChunkMetadata) -> str:
    if not chunk_has_image_source(chunk):
        return chunk.content
    parts = [
        chunk.description,
        strip_visible_image_references(chunk.content),
        " > ".join(chunk.heading_path or []),
        chunk.source_locator,
    ]
    return join_unique_text_parts(parts) or chunk.content


def build_display_chunk_text(chunk: ChunkMetadata) -> str:
    if chunk_has_image_source(chunk) and chunk.description:
        return chunk.description
    return chunk.content


def join_unique_text_parts(parts: list[str | None]) -> str:
    cleaned_parts: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = " ".join((part or "").split())
        if not cleaned or cleaned in seen:
            continue
        cleaned_parts.append(cleaned)
        seen.add(cleaned)
    return "\n\n".join(cleaned_parts)
