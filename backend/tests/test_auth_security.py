from datetime import timedelta

import pytest

from app.core.errors import ApiError
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_uses_bcrypt_and_verifies() -> None:
    password_hash = hash_password("AdminPassword123")

    assert password_hash.startswith("$2")
    assert verify_password("AdminPassword123", password_hash)
    assert not verify_password("wrong-password", password_hash)


def test_jwt_access_and_refresh_tokens_include_expected_type() -> None:
    access_token = create_access_token("user-id")
    refresh_token = create_refresh_token("user-id")

    access_payload = decode_token(access_token, expected_type=ACCESS_TOKEN_TYPE)
    refresh_payload = decode_token(refresh_token, expected_type=REFRESH_TOKEN_TYPE)
    assert access_payload["sub"] == "user-id"
    assert refresh_payload["sub"] == "user-id"
    assert access_payload["jti"]
    assert refresh_payload["jti"]

    with pytest.raises(ApiError) as exc_info:
        decode_token(access_token, expected_type=REFRESH_TOKEN_TYPE)

    assert exc_info.value.code == "UNAUTHORIZED"


def test_expired_jwt_is_rejected() -> None:
    token = create_token(
        subject="user-id", token_type=ACCESS_TOKEN_TYPE, expires_delta=timedelta(seconds=-1)
    )

    with pytest.raises(ApiError) as exc_info:
        decode_token(token, expected_type=ACCESS_TOKEN_TYPE)

    assert exc_info.value.code == "UNAUTHORIZED"
