from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_admin_user
from app.db.session import get_db
from app.models import User, UserRole
from app.schemas.auth import AuthUserResponse
from app.schemas.users import (
    ResetPasswordRequest,
    ResetPasswordResponse,
    UserCreateRequest,
    UserListResponse,
    UserUpdateRequest,
)
from app.services.users import (
    create_user,
    disable_user,
    enable_user,
    list_users,
    reset_password,
    update_user,
)

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=UserListResponse)
def read_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = None,
    role: UserRole | None = None,
    is_active: bool | None = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin_user),
) -> UserListResponse:
    return list_users(
        db,
        page=page,
        page_size=page_size,
        keyword=keyword,
        role=role,
        is_active=is_active,
    )


@router.post("", response_model=AuthUserResponse, status_code=201)
def create_user_endpoint(
    payload: UserCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> AuthUserResponse:
    return create_user(
        db,
        payload,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.patch("/{user_id}", response_model=AuthUserResponse)
def update_user_endpoint(
    user_id: UUID,
    payload: UserUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> AuthUserResponse:
    return update_user(
        db,
        user_id,
        payload,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/{user_id}/disable", response_model=AuthUserResponse)
def disable_user_endpoint(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> AuthUserResponse:
    return disable_user(
        db,
        user_id,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/{user_id}/enable", response_model=AuthUserResponse)
def enable_user_endpoint(
    user_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> AuthUserResponse:
    return enable_user(
        db,
        user_id,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


@router.post("/{user_id}/reset-password", response_model=ResetPasswordResponse)
def reset_password_endpoint(
    user_id: UUID,
    payload: ResetPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin_user),
) -> ResetPasswordResponse:
    return reset_password(
        db,
        user_id,
        payload.new_password,
        actor=admin,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
    )


def get_request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None
