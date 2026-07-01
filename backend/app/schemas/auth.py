from datetime import datetime

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str


class ConsumerSessionRequest(BaseModel):
    session_id: str
    display_name: str | None = None
    username: str | None = None


class ConsumerUserOption(BaseModel):
    username: str
    display_name: str


class ConsumerUserOptionsResponse(BaseModel):
    items: list[ConsumerUserOption]


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class AuthUserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class LoginResponse(TokenResponse):
    user: AuthUserResponse
