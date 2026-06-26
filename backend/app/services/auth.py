from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
)
from app.models import RevokedRefreshToken, User, UserProfile, UserRole, UserStatus
from app.schemas.auth import (
    AuthUserResponse,
    ConsumerUserOption,
    ConsumerUserOptionsResponse,
    LoginResponse,
    TokenResponse,
)


def get_user_by_username(db: Session, username: str) -> User | None:
    return db.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.username == username, User.deleted_at.is_(None))
    )


def get_user_by_id(db: Session, user_id: UUID) -> User | None:
    return db.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.id == user_id, User.deleted_at.is_(None))
    )


def create_default_admin(db: Session) -> User | None:
    settings = get_settings()
    existing_admin = db.scalar(
        select(User).where(
            (User.username == settings.default_admin_username)
            | (User.email == settings.default_admin_email)
        )
    )
    if existing_admin is not None:
        return None

    admin = User(
        email=settings.default_admin_email,
        username=settings.default_admin_username,
        password_hash=hash_password(settings.default_admin_password),
        role=UserRole.ADMIN.value,
        status=UserStatus.ACTIVE.value,
    )
    admin.profile = UserProfile(display_name=settings.default_admin_display_name)
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin


def create_or_update_default_consumer(db: Session) -> User:
    settings = get_settings()
    user = db.scalar(
        select(User)
        .options(selectinload(User.profile))
        .where(User.username == settings.default_consumer_username)
    )
    if user is not None and user.role != UserRole.USER.value:
        raise ApiError(
            code="CONFIGURATION_ERROR",
            message="Default consumer username is already used by a non-user account.",
            status_code=500,
        )

    if user is None:
        user = User(
            email=settings.default_consumer_email,
            username=settings.default_consumer_username,
            password_hash=hash_password(f"{settings.jwt_secret_key}:consumer-session"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        user.profile = UserProfile(display_name=settings.default_consumer_display_name)
        db.add(user)
    else:
        user.status = UserStatus.ACTIVE.value
        user.deleted_at = None
        user.failed_login_count = 0
        user.locked_until = None
        if user.profile is None:
            user.profile = UserProfile(display_name=settings.default_consumer_display_name)
        elif not user.profile.display_name:
            user.profile.display_name = settings.default_consumer_display_name

    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return user


def list_consumer_user_options(db: Session) -> ConsumerUserOptionsResponse:
    users = db.scalars(
        select(User)
        .outerjoin(User.profile)
        .options(selectinload(User.profile))
        .where(
            User.deleted_at.is_(None),
            User.role == UserRole.USER.value,
            User.status == UserStatus.ACTIVE.value,
        )
        .order_by(UserProfile.display_name.asc(), User.username.asc())
    ).all()
    return ConsumerUserOptionsResponse(
        items=[
            ConsumerUserOption(
                username=user.username,
                display_name=(
                    user.profile.display_name
                    if user.profile and user.profile.display_name
                    else user.username
                ),
            )
            for user in users
        ]
    )


def create_consumer_session(db: Session, *, username: str | None = None) -> LoginResponse:
    if username is None:
        return build_login_response(create_or_update_default_consumer(db))

    user = get_user_by_username(db, username)
    if user is None or user.role != UserRole.USER.value:
        raise ApiError(
            code="RESOURCE_NOT_FOUND",
            message="Consumer user was not found.",
            status_code=404,
        )
    if user.status == UserStatus.DISABLED.value:
        raise ApiError(
            code="ACCOUNT_DISABLED",
            message="Account is disabled.",
            status_code=403,
        )

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(user)
    return build_login_response(user)


def authenticate_user(db: Session, *, username: str, password: str) -> LoginResponse:
    settings = get_settings()
    user = get_user_by_username(db, username)
    if user is None:
        raise ApiError(
            code="INVALID_CREDENTIALS",
            message="Username or password is incorrect.",
            status_code=401,
        )

    now = datetime.now(UTC)
    if user.locked_until is not None and _ensure_aware(user.locked_until) > now:
        raise ApiError(
            code="ACCOUNT_LOCKED",
            message="Account is temporarily locked.",
            status_code=423,
        )

    if user.status == UserStatus.DISABLED.value:
        raise ApiError(
            code="ACCOUNT_DISABLED",
            message="Account is disabled.",
            status_code=403,
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.login_failure_lock_threshold:
            user.locked_until = now + timedelta(minutes=settings.login_lock_minutes)
            db.commit()
            raise ApiError(
                code="ACCOUNT_LOCKED",
                message="Account is temporarily locked.",
                status_code=423,
            )

        db.commit()
        raise ApiError(
            code="INVALID_CREDENTIALS",
            message="Username or password is incorrect.",
            status_code=401,
        )

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    db.refresh(user)
    return build_login_response(user)


def build_login_response(user: User) -> LoginResponse:
    settings = get_settings()
    return LoginResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
        user=build_auth_user_response(user),
    )


def build_token_response(user: User) -> TokenResponse:
    settings = get_settings()
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=settings.access_token_expire_minutes * 60,
    )


def ensure_refresh_token_not_revoked(db: Session, token_jti: str) -> None:
    revoked_token = db.scalar(
        select(RevokedRefreshToken).where(RevokedRefreshToken.jti == token_jti)
    )
    if revoked_token is not None:
        raise ApiError(
            code="UNAUTHORIZED",
            message="Refresh token has been revoked.",
            status_code=401,
        )


def revoke_refresh_token(db: Session, *, token_payload: dict[str, Any]) -> None:
    token_jti = str(token_payload["jti"])
    ensure_refresh_token_not_revoked(db, token_jti)

    expires_at = datetime.fromtimestamp(int(token_payload["exp"]), tz=UTC)
    revoked_token = RevokedRefreshToken(
        jti=token_jti,
        user_id=UUID(str(token_payload["sub"])),
        expires_at=expires_at,
    )
    db.add(revoked_token)
    db.commit()


def build_auth_user_response(user: User) -> AuthUserResponse:
    display_name = (
        user.profile.display_name if user.profile and user.profile.display_name else user.username
    )
    return AuthUserResponse(
        id=str(user.id),
        username=user.username,
        display_name=display_name,
        role=user.role,
        is_active=user.status == UserStatus.ACTIVE.value,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


def require_active_user(user: User | None) -> User:
    if user is None:
        raise ApiError(code="UNAUTHORIZED", message="Token is invalid.", status_code=401)
    if user.status == UserStatus.DISABLED.value:
        raise ApiError(code="ACCOUNT_DISABLED", message="Account is disabled.", status_code=403)
    return user


def _ensure_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
