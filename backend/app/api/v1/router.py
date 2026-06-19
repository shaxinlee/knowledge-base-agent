from fastapi import APIRouter

from app.api.v1.assistant_profile import router as assistant_profile_router
from app.api.v1.audit_logs import router as audit_logs_router
from app.api.v1.auth import router as auth_router
from app.api.v1.conversations import router as conversations_router
from app.api.v1.feedback import router as feedback_router
from app.api.v1.files import router as files_router
from app.api.v1.health import router as health_router
from app.api.v1.knowledge_bases import router as knowledge_bases_router
from app.api.v1.model_settings import router as model_settings_router
from app.api.v1.retrieval import router as retrieval_router
from app.api.v1.users import router as users_router

api_router = APIRouter()
api_router.include_router(assistant_profile_router)
api_router.include_router(audit_logs_router)
api_router.include_router(auth_router)
api_router.include_router(conversations_router)
api_router.include_router(feedback_router)
api_router.include_router(files_router)
api_router.include_router(health_router)
api_router.include_router(knowledge_bases_router)
api_router.include_router(model_settings_router)
api_router.include_router(retrieval_router)
api_router.include_router(users_router)
