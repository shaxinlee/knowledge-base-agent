from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    DocumentSummary,
    File,
    FileStatus,
    KnowledgeBase,
    KnowledgeBaseCommunitySummary,
)
from app.rag.query_router import is_overall_query
from app.services.object_storage import ObjectStorage

OVERALL_PROMPT_VERSION = "knowledge-overall-v2"
LIVE_SUMMARY_MARKER = "<!-- knowledge-overall-live-summaries -->"


def is_knowledge_overall_query(query: str) -> bool:
    return is_overall_query(query)


def rebuild_knowledge_base_overall(
    db: Session,
    *,
    knowledge_base_id: UUID,
    storage: ObjectStorage,
) -> str:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        return ""

    files = list(
        db.scalars(
            select(File)
            .where(
                File.knowledge_base_id == knowledge_base_id,
                File.deleted_at.is_(None),
            )
            .order_by(File.created_at.asc(), File.file_name.asc())
        ).all()
    )
    generated_at = datetime.now(UTC)
    content = render_overall_markdown(
        knowledge_base=knowledge_base,
        files=files,
    )
    bucket = get_settings().normalized_docs_bucket
    key = build_overall_storage_key(knowledge_base_id)
    storage.put_object(
        bucket=bucket,
        key=key,
        data=content.encode("utf-8"),
        content_type="text/markdown; charset=utf-8",
        metadata={
            "knowledge_base_id": str(knowledge_base_id),
            "generated_at": generated_at.isoformat(),
            "purpose": "knowledge_base_overall",
        },
    )
    settings = dict(knowledge_base.settings or {})
    settings["overall"] = {
        "bucket": bucket,
        "key": key,
        "generated_at": generated_at.isoformat(),
        "file_count": len(files),
        "indexed_file_count": sum(1 for file in files if file.status == FileStatus.INDEXED.value),
    }
    knowledge_base.settings = settings
    db.commit()
    return content


def read_knowledge_base_overall(
    db: Session,
    *,
    knowledge_base_id: UUID,
    storage: ObjectStorage,
) -> str:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        return ""
    overall = (knowledge_base.settings or {}).get("overall")
    if not isinstance(overall, dict):
        return rebuild_knowledge_base_overall(
            db,
            knowledge_base_id=knowledge_base_id,
            storage=storage,
        )
    bucket = str(overall.get("bucket") or get_settings().normalized_docs_bucket)
    key = str(overall.get("key") or build_overall_storage_key(knowledge_base_id))
    try:
        base_content = storage.get_object(bucket=bucket, key=key).decode("utf-8")
    except Exception:
        base_content = rebuild_knowledge_base_overall(
            db,
            knowledge_base_id=knowledge_base_id,
            storage=storage,
        )
    return append_live_summary_context(
        db,
        knowledge_base_id=knowledge_base_id,
        base_content=base_content,
    )


def build_knowledge_overall_answer(overall_content: str) -> str:
    content = overall_content.strip()
    if not content:
        return "当前知识库还没有可用于概览的文件信息。"
    return content


def build_overall_storage_key(knowledge_base_id: UUID) -> str:
    return f"knowledge-bases/{knowledge_base_id}/overall.md"


def append_live_summary_context(
    db: Session,
    *,
    knowledge_base_id: UUID,
    base_content: str,
) -> str:
    knowledge_base = db.get(KnowledgeBase, knowledge_base_id)
    if knowledge_base is None:
        return base_content

    files = list(
        db.scalars(
            select(File)
            .where(
                File.knowledge_base_id == knowledge_base_id,
                File.deleted_at.is_(None),
            )
            .order_by(File.created_at.asc(), File.file_name.asc())
        ).all()
    )
    community_summary = db.scalar(
        select(KnowledgeBaseCommunitySummary).where(
            KnowledgeBaseCommunitySummary.knowledge_base_id == knowledge_base_id
        )
    )
    summary_rows = db.execute(
        select(DocumentSummary, File)
        .join(File, File.id == DocumentSummary.file_id)
        .where(
            DocumentSummary.knowledge_base_id == knowledge_base_id,
            File.deleted_at.is_(None),
            File.latest_parse_job_id == DocumentSummary.parse_job_id,
        )
    ).all()
    summaries_by_file_id = {
        file.id: summary
        for summary, file in summary_rows
    }

    clean_base = base_content.split(LIVE_SUMMARY_MARKER, maxsplit=1)[0].rstrip()
    lines = [
        clean_base,
        "",
        LIVE_SUMMARY_MARKER,
        "",
        "## 知识库社区摘要",
        "",
    ]
    if community_summary is not None and community_summary.summary:
        lines.append(community_summary.summary.strip())
    elif community_summary is not None and community_summary.status in {"pending", "running"}:
        lines.append("社区摘要正在生成中。")
    elif community_summary is not None and community_summary.status == "failed":
        lines.append("社区摘要生成失败，当前先提供各文档摘要。")
    else:
        lines.append("当前还没有可用的社区摘要。")

    lines.extend(["", "## 各文档摘要", ""])
    if not files:
        lines.append("当前知识库暂无文档。")
    for index, file in enumerate(files, start=1):
        summary = summaries_by_file_id.get(file.id)
        lines.append(f"### {index}. {file.file_name}")
        lines.append("")
        if summary is not None and summary.summary:
            lines.append(summary.summary.strip())
            if summary.status == "partially_completed":
                lines.append("")
                lines.append(
                    f"注：该摘要基于部分成功 Chunk 生成，"
                    f"仍有 {summary.chunk_failed} 个 Chunk 未成功。"
                )
        elif summary is not None and summary.status in {"pending", "running"}:
            lines.append("文档摘要正在生成中。")
        elif summary is not None and summary.status == "failed":
            lines.append("文档摘要生成失败，暂时没有可用摘要。")
        else:
            lines.append("当前文档还没有可用摘要。")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_overall_markdown(
    *,
    knowledge_base: KnowledgeBase,
    files: list[File],
) -> str:
    lines = [
        f"# {knowledge_base.name} 知识库概览",
        "",
        f"知识库创建时间 {format_overall_datetime(knowledge_base.created_at)}",
        "",
        f"文件数量 {len(files)}",
        "",
        "知识库包含的文件：",
        "",
        "| 序号 | 文件名称 | 文件添加时间 |",
        "| ---: | --- | --- |",
    ]
    if not files:
        lines.append("| - | 暂无文件 | - |")
    for index, file in enumerate(files, start=1):
        lines.append(
            "| "
            f"{index} | "
            f"{escape_markdown_table_cell(file.file_name)} | "
            f"{format_overall_datetime(file.created_at)} |"
        )
    return "\n".join(lines).strip() + "\n"


def format_overall_datetime(value: datetime) -> str:
    return value.isoformat()


def escape_markdown_table_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ")
