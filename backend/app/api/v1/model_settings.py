from fastapi import APIRouter, Depends

from app.api.deps import require_admin_user
from app.models import User
from app.schemas.model_settings import ModelSettingsResponse, ModelSettingsUpdateRequest
from app.services.model_settings import get_model_settings, update_model_settings

router = APIRouter(prefix="/model-settings", tags=["Model Settings"])


@router.get("", response_model=ModelSettingsResponse)
def read_model_settings(
    _admin: User = Depends(require_admin_user),
) -> ModelSettingsResponse:
    return get_model_settings()


@router.patch("", response_model=ModelSettingsResponse)
def update_model_settings_endpoint(
    payload: ModelSettingsUpdateRequest,
    _admin: User = Depends(require_admin_user),
) -> ModelSettingsResponse:
    return update_model_settings(payload)
