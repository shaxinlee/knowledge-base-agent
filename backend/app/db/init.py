import logging

from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.services.auth import create_default_admin

logger = logging.getLogger(__name__)


def init_default_admin() -> None:
    try:
        with SessionLocal() as db:
            admin = create_default_admin(db)
    except SQLAlchemyError:
        logger.exception("Failed to initialize default admin.")
        return

    if admin is not None:
        logger.info("Default admin user initialized.")
