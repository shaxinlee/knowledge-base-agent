from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import ColumnElement

from app.core.errors import ApiError
from app.core.security import hash_password
from app.models import User, UserProfile, UserRole, UserStatus
from app.schemas.auth import AuthUserResponse
from app.schemas.users import (
    ResetPasswordResponse,
    UserCreateRequest,
    UserListResponse,
    UserUpdateRequest,
)
from app.services.auth import build_auth_user_response, get_user_by_id
from app.services.audit_logs import create_audit_log


def list_users(
    db: Session,
    *,
    page: int,
    page_size: int,
    keyword: str | None,
    role: UserRole | None,
    is_active: bool | None,
) -> UserListResponse:
    normalized_page = max(page, 1)
    normalized_page_size = min(max(page_size, 1), 100)
    filters: list[ColumnElement[bool]] = [User.deleted_at.is_(None)]

    if keyword:
        pattern = f"%{keyword}%"
        filters.append(
            or_(
                User.username.ilike(pattern),
                UserProfile.display_name.ilike(pattern),
            )
        )
    if role is not None:
        filters.append(User.role == role.value)
    if is_active is not None:
        filters.append(
            User.status == (UserStatus.ACTIVE.value if is_active else UserStatus.DISABLED.value)
        )

    base_query = select(User).outerjoin(User.profile).where(*filters)
    total = db.scalar(select(func.count()).select_from(base_query.subquery())) or 0
    users = db.scalars(
        base_query.options(selectinload(User.profile))
        .order_by(User.created_at.desc())
        .offset((normalized_page - 1) * normalized_page_size)
        .limit(normalized_page_size)
    ).all()

    return UserListResponse(
        items=[build_auth_user_response(user) for user in users],
        total=total,
        page=normalized_page,
        page_size=normalized_page_size,
    )


def create_user(
    db: Session,
    payload: UserCreateRequest,
    *,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthUserResponse:
    ensure_user_identity_available(db, email=payload.email, username=payload.username)

    user = User(
        email=payload.email,
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role.value,
        status=UserStatus.ACTIVE.value,
    )
    user.profile = UserProfile(display_name=payload.display_name)
    db.add(user)
    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="create_user",
        resource_type="user",
        resource_id=user.id,
        details={"after": build_user_audit_snapshot(user)},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(user)
    return build_auth_user_response(user)


def update_user(
    db: Session,
    user_id: UUID,
    payload: UserUpdateRequest,
    *,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthUserResponse:
    user = require_user(db, user_id)
    before = build_user_audit_snapshot(user)

    if payload.role is not None:
        user.role = payload.role.value
    if payload.display_name is not None:
        if user.profile is None:
            user.profile = UserProfile(display_name=payload.display_name)
        else:
            user.profile.display_name = payload.display_name

    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="update_user",
        resource_type="user",
        resource_id=user.id,
        details={"before": before, "after": build_user_audit_snapshot(user)},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(user)
    return build_auth_user_response(user)


def disable_user(
    db: Session,
    user_id: UUID,
    *,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthUserResponse:
    user = require_user(db, user_id)
    before = build_user_audit_snapshot(user)
    user.status = UserStatus.DISABLED.value
    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="disable_user",
        resource_type="user",
        resource_id=user.id,
        details={"before": before, "after": build_user_audit_snapshot(user)},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(user)
    return build_auth_user_response(user)


def enable_user(
    db: Session,
    user_id: UUID,
    *,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> AuthUserResponse:
    user = require_user(db, user_id)
    before = build_user_audit_snapshot(user)
    user.status = UserStatus.ACTIVE.value
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="enable_user",
        resource_type="user",
        resource_id=user.id,
        details={"before": before, "after": build_user_audit_snapshot(user)},
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    db.refresh(user)
    return build_auth_user_response(user)


def reset_password(
    db: Session,
    user_id: UUID,
    new_password: str,
    *,
    actor: User,
    ip_address: str | None,
    user_agent: str | None,
) -> ResetPasswordResponse:
    user = require_user(db, user_id)
    before = build_user_audit_snapshot(user)
    user.password_hash = hash_password(new_password)
    user.failed_login_count = 0
    user.locked_until = None
    reset_at = datetime.now(UTC)
    db.flush()
    create_audit_log(
        db,
        actor_id=actor.id,
        action="reset_user_password",
        resource_type="user",
        resource_id=user.id,
        details={
            "before": before,
            "after": build_user_audit_snapshot(user),
            "password_changed": True,
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return ResetPasswordResponse(user_id=str(user.id), reset_at=reset_at)


def require_user(db: Session, user_id: UUID) -> User:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="User was not found.",
            status_code=404,
        )
    return user


def ensure_user_identity_available(db: Session, *, email: str, username: str) -> None:
    existing = db.scalar(
        select(User).where(
            User.deleted_at.is_(None),
            or_(User.email == email, User.username == username),
        )
    )
    if existing is None:
        return

    details = {
        "email": existing.email == email,
        "username": existing.username == username,
    }
    raise ApiError(
        code="VALIDATION_ERROR",
        message="Email or username is already in use.",
        status_code=409,
        details=details,
    )


def build_user_audit_snapshot(user: User) -> dict[str, str | int | None]:
    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "display_name": user.profile.display_name if user.profile else None,
        "role": user.role,
        "status": user.status,
        "failed_login_count": user.failed_login_count,
    }
