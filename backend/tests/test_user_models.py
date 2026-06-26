from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint

from app.db.base import Base
from app.models import UserRole, UserStatus
import app.models  # noqa: F401


def test_user_role_and_status_values_match_sdd() -> None:
    assert {role.value for role in UserRole} == {"admin", "user"}
    assert {status.value for status in UserStatus} == {"active", "disabled"}


def test_users_table_matches_sdd_core_columns_and_constraints() -> None:
    users = Base.metadata.tables["users"]

    assert {
        "id",
        "email",
        "username",
        "password_hash",
        "role",
        "status",
        "failed_login_count",
        "locked_until",
        "last_login_at",
        "created_at",
        "updated_at",
        "deleted_at",
    } == set(users.columns.keys())
    assert users.columns["id"].primary_key
    assert not users.columns["email"].nullable
    assert not users.columns["username"].nullable
    assert not users.columns["password_hash"].nullable
    assert not users.columns["role"].nullable
    assert not users.columns["status"].nullable
    assert users.columns["failed_login_count"].default is not None

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in users.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("email",) in unique_columns
    assert ("username",) in unique_columns

    check_names = {
        constraint.name
        for constraint in users.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert "ck_users_role_valid" in check_names
    assert "ck_users_status_valid" in check_names


def test_user_profiles_table_matches_sdd_core_columns_and_constraints() -> None:
    profiles = Base.metadata.tables["user_profiles"]

    assert {
        "id",
        "user_id",
        "display_name",
        "occupation",
        "answer_style",
        "preferences",
        "created_at",
        "updated_at",
    } == set(profiles.columns.keys())
    assert profiles.columns["id"].primary_key
    assert not profiles.columns["user_id"].nullable

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in profiles.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("user_id",) in unique_columns

    foreign_keys = {
        constraint.elements[0].target_fullname
        for constraint in profiles.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert "users.id" in foreign_keys


def test_revoked_refresh_tokens_table_supports_logout_revoke() -> None:
    tokens = Base.metadata.tables["revoked_refresh_tokens"]

    assert {
        "id",
        "jti",
        "user_id",
        "expires_at",
        "revoked_at",
        "created_at",
    } == set(tokens.columns.keys())
    assert tokens.columns["id"].primary_key
    assert not tokens.columns["jti"].nullable
    assert not tokens.columns["user_id"].nullable
    assert not tokens.columns["expires_at"].nullable

    unique_columns = {
        tuple(column.name for column in constraint.columns)
        for constraint in tokens.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("jti",) in unique_columns

    foreign_keys = {
        constraint.elements[0].target_fullname
        for constraint in tokens.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }
    assert "users.id" in foreign_keys
