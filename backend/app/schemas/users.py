from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole
from app.schemas.auth import AuthUserResponse


class UserListResponse(BaseModel):
    items: list[AuthUserResponse]
    total: int
    page: int
    page_size: int


class UserCreateRequest(BaseModel):
    email: str
    username: str
    display_name: str
    password: str = Field(min_length=8)
    role: UserRole


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    role: UserRole | None = None


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=8)


class ResetPasswordResponse(BaseModel):
    user_id: str
    reset_at: datetime

    model_config = ConfigDict(from_attributes=True)
