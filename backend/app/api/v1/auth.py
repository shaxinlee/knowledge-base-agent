from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import ApiError
from app.core.security import REFRESH_TOKEN_TYPE, decode_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    AuthUserResponse,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
)
from app.services.auth import (
    authenticate_user,
    build_auth_user_response,
    build_token_response,
    ensure_refresh_token_not_revoked,
    get_user_by_id,
    require_active_user,
    revoke_refresh_token,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    return authenticate_user(db, username=payload.username, password=payload.password)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(payload: RefreshTokenRequest, db: Session = Depends(get_db)) -> TokenResponse:
    token_payload = decode_token(payload.refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    ensure_refresh_token_not_revoked(db, str(token_payload["jti"]))
    try:
        user_id = UUID(str(token_payload["sub"]))
    except ValueError as exc:
        raise ApiError(
            code="UNAUTHORIZED", message="Token subject is invalid.", status_code=401
        ) from exc

    user = require_active_user(get_user_by_id(db, user_id))
    return build_token_response(user)


@router.post("/logout", status_code=204)
def logout(
    payload: LogoutRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    token_payload = decode_token(payload.refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    try:
        refresh_user_id = UUID(str(token_payload["sub"]))
    except ValueError as exc:
        raise ApiError(
            code="UNAUTHORIZED", message="Token subject is invalid.", status_code=401
        ) from exc

    if refresh_user_id != current_user.id:
        raise ApiError(
            code="UNAUTHORIZED",
            message="Refresh token does not belong to the current user.",
            status_code=401,
        )

    require_active_user(get_user_by_id(db, refresh_user_id))
    revoke_refresh_token(db, token_payload=token_payload)
    return Response(status_code=204)


@router.get("/me", response_model=AuthUserResponse)
def read_me(current_user: User = Depends(get_current_user)) -> AuthUserResponse:
    return build_auth_user_response(current_user)
