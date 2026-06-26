from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import KnowledgeBase, KnowledgeBaseStatus
from app.services.knowledge_overall import rebuild_knowledge_base_overall
from app.services.object_storage import get_object_storage


def main() -> None:
    storage = get_object_storage()
    with SessionLocal() as db:
        knowledge_bases = db.scalars(
            select(KnowledgeBase)
            .where(
                KnowledgeBase.status == KnowledgeBaseStatus.ACTIVE.value,
                KnowledgeBase.deleted_at.is_(None),
            )
            .order_by(KnowledgeBase.created_at.asc())
        ).all()
        for knowledge_base in knowledge_bases:
            rebuild_knowledge_base_overall(
                db,
                knowledge_base_id=knowledge_base.id,
                storage=storage,
            )
            print(f"rebuilt overall for {knowledge_base.id} {knowledge_base.name}")


if __name__ == "__main__":
    main()
