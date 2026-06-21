import argparse
from uuid import UUID

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import File, ParseJob
from app.services.document_summaries import (
    PRIORITY_BACKFILL,
    enqueue_document_summary,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Queue document summaries for existing files.")
    parser.add_argument("--file-id", type=UUID)
    parser.add_argument("--knowledge-base-id", type=UUID)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    queued = 0
    not_ready = 0
    skipped = 0
    with SessionLocal() as db:
        query = select(File).where(File.deleted_at.is_(None))
        if args.file_id:
            query = query.where(File.id == args.file_id)
        if args.knowledge_base_id:
            query = query.where(File.knowledge_base_id == args.knowledge_base_id)
        files = list(db.scalars(query.order_by(File.created_at.asc())).all())
        for file in files:
            if file.latest_parse_job_id is None:
                skipped += 1
                continue
            parse_job = db.get(ParseJob, file.latest_parse_job_id)
            if parse_job is None:
                skipped += 1
                continue
            summary = enqueue_document_summary(
                db,
                file=file,
                parse_job=parse_job,
                priority=PRIORITY_BACKFILL,
                force=args.force,
            )
            if summary.status == "not_ready":
                not_ready += 1
            else:
                queued += 1
        db.commit()
    print(
        f"document summary backfill: files={len(files)} queued={queued} "
        f"not_ready={not_ready} skipped={skipped} force={args.force}"
    )


if __name__ == "__main__":
    main()
