from collections.abc import Generator
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import AuditLog, User, UserProfile, UserRole, UserStatus
from app.services.auth import create_default_admin


def _make_session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _override_db(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def _install_db_override(session_factory: sessionmaker[Session]) -> None:
    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _create_default_admin(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        create_default_admin(db)


def test_admin_can_create_list_update_disable_enable_and_reset_user() -> None:
    session_factory = _make_session_factory()
    _create_default_admin(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        headers = {"Authorization": f"Bearer {admin_token}"}

        create_response = client.post(
            "/api/v1/users",
            headers=headers,
            json={
                "email": "alice@example.local",
                "username": "alice",
                "display_name": "Alice",
                "password": "InitialPassword123",
                "role": "user",
            },
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["username"] == "alice"
        assert created["display_name"] == "Alice"
        assert created["role"] == "user"
        assert created["is_active"] is True

        list_response = client.get("/api/v1/users?keyword=Alice", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["username"] == "alice"

        update_response = client.patch(
            f"/api/v1/users/{created['id']}",
            headers=headers,
            json={"display_name": "Alice Zhang", "role": "admin"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["display_name"] == "Alice Zhang"
        assert update_response.json()["role"] == "admin"

        disable_response = client.post(f"/api/v1/users/{created['id']}/disable", headers=headers)
        assert disable_response.status_code == 200
        assert disable_response.json()["is_active"] is False

        disabled_login = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "InitialPassword123"},
        )
        assert disabled_login.status_code == 403
        assert disabled_login.json()["error"]["code"] == "ACCOUNT_DISABLED"

        enable_response = client.post(f"/api/v1/users/{created['id']}/enable", headers=headers)
        assert enable_response.status_code == 200
        assert enable_response.json()["is_active"] is True

        reset_response = client.post(
            f"/api/v1/users/{created['id']}/reset-password",
            headers=headers,
            json={"new_password": "NewPassword123"},
        )
        assert reset_response.status_code == 200
        assert reset_response.json()["user_id"] == created["id"]

        new_login = client.post(
            "/api/v1/auth/login",
            json={"username": "alice", "password": "NewPassword123"},
        )
        assert new_login.status_code == 200

        with session_factory() as db:
            audit_logs = db.query(AuditLog).order_by(AuditLog.created_at).all()
        actions = [audit_log.action for audit_log in audit_logs]
        assert actions == [
            "create_user",
            "update_user",
            "disable_user",
            "enable_user",
            "reset_user_password",
        ]
        assert {audit_log.resource_type for audit_log in audit_logs} == {"user"}
        assert {str(audit_log.resource_id) for audit_log in audit_logs} == {created["id"]}
        assert all(audit_log.details for audit_log in audit_logs)
        reset_details = cast(dict[str, Any], audit_logs[-1].details)
        assert reset_details["password_changed"] is True
        assert "NewPassword123" not in str(reset_details)
        assert "password_hash" not in str(reset_details)
    finally:
        app.dependency_overrides.clear()


def test_user_cannot_access_admin_users_api() -> None:
    session_factory = _make_session_factory()
    _create_default_admin(session_factory)
    with session_factory() as db:
        user = User(
            email="bob@example.local",
            username="bob",
            password_hash=hash_password("BobPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        user.profile = UserProfile(display_name="Bob")
        db.add(user)
        db.commit()

    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        user_token = _login(client, "bob", "BobPassword123")

        response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {user_token}"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()


def test_duplicate_email_or_username_is_rejected() -> None:
    session_factory = _make_session_factory()
    _create_default_admin(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        payload = {
            "email": "duplicate@example.local",
            "username": "duplicate",
            "display_name": "Duplicate",
            "password": "InitialPassword123",
            "role": "user",
        }

        first_response = client.post("/api/v1/users", headers=headers, json=payload)
        second_response = client.post("/api/v1/users", headers=headers, json=payload)

        assert first_response.status_code == 201
        assert second_response.status_code == 409
        assert second_response.json()["error"]["code"] == "VALIDATION_ERROR"
    finally:
        app.dependency_overrides.clear()
