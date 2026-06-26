import logging

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_admin_user
from app.models import User
from app.schemas.model_settings import ModelSettingsResponse, ModelSettingsUpdateRequest
from app.services.model_settings import get_model_settings, update_model_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model-settings", tags=["Model Settings"])


@router.get("", response_model=ModelSettingsResponse)
def read_model_settings(
    _admin: User = Depends(require_admin_user),
) -> ModelSettingsResponse:
    return get_model_settings()


@router.patch("", response_model=ModelSettingsResponse)
async def update_model_settings_endpoint(
    payload: ModelSettingsUpdateRequest,
    request: Request,
    _admin: User = Depends(require_admin_user),
) -> ModelSettingsResponse:
    result = update_model_settings(payload)

    # Reload LLM clients on running workers so new model settings take effect
    # immediately without requiring a container restart.
    summary_worker = getattr(request.app.state, "document_summary_worker", None)
    if summary_worker is not None and summary_worker._task is not None:
        try:
            await summary_worker.reload_client()
        except Exception:
            logger.exception("Failed to reload document summary worker client")

    graph_worker = getattr(request.app.state, "knowledge_graph_worker", None)
    if graph_worker is not None and graph_worker._task is not None:
        try:
            await graph_worker.reload_llm_client()
        except Exception:
            logger.exception("Failed to reload knowledge graph worker client")

    return result
