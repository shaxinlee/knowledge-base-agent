from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.security import ACCESS_TOKEN_TYPE, decode_token
from app.db.session import get_db
from app.models import User, UserRole
from app.services.auth import get_user_by_id, require_active_user

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise ApiError(
            code="UNAUTHORIZED", message="Authorization token is required.", status_code=401
        )

    payload = decode_token(credentials.credentials, expected_type=ACCESS_TOKEN_TYPE)
    try:
        user_id = UUID(str(payload["sub"]))
    except ValueError as exc:
        raise ApiError(
            code="UNAUTHORIZED", message="Token subject is invalid.", status_code=401
        ) from exc

    return require_active_user(get_user_by_id(db, user_id))


def require_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != UserRole.ADMIN.value:
        raise ApiError(code="FORBIDDEN", message="Admin permission is required.", status_code=403)
    return current_user
