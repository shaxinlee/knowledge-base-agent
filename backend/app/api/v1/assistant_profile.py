from fastapi import APIRouter, Depends

from app.api.deps import require_admin_user
from app.models import User
from app.schemas.assistant_profile import (
    AssistantProfileResponse,
    AssistantProfileUpdateRequest,
)
from app.services.assistant_profile import (
    get_assistant_profile,
    update_assistant_profile,
)

router = APIRouter(prefix="/assistant-profile", tags=["Assistant Profile"])


@router.get("", response_model=AssistantProfileResponse)
def read_assistant_profile(
    _admin: User = Depends(require_admin_user),
) -> AssistantProfileResponse:
    return get_assistant_profile()


@router.patch("", response_model=AssistantProfileResponse)
def update_assistant_profile_endpoint(
    payload: AssistantProfileUpdateRequest,
    _admin: User = Depends(require_admin_user),
) -> AssistantProfileResponse:
    return update_assistant_profile(payload)
