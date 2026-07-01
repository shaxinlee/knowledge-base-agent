import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import SessionLocal
from app.services.auth import create_default_admin

logger = logging.getLogger(__name__)


def run_migrations() -> None:
    alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    if not alembic_ini.exists():
        logger.warning("alembic.ini not found at %s, skipping auto-migration.", alembic_ini)
        return
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(alembic_ini.parent / "migrations"))
    try:
        command.upgrade(cfg, "head")
        logger.info("Database migrations applied successfully.")
    except Exception:
        logger.exception("Failed to apply database migrations.")


def init_default_admin() -> None:
    try:
        with SessionLocal() as db:
            admin = create_default_admin(db)
    except SQLAlchemyError:
        logger.exception("Failed to initialize default admin.")
        return

    if admin is not None:
        logger.info("Default admin user initialized.")
