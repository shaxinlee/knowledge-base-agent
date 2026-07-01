from collections.abc import Generator
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import User, UserProfile, UserRole, UserStatus
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


def test_login_refresh_and_me_with_default_admin() -> None:
    session_factory = _make_session_factory()
    with session_factory() as db:
        create_default_admin(db)

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "AdminPassword123"},
        )
        assert login_response.status_code == 200
        login_body = login_response.json()
        assert login_body["token_type"] == "bearer"
        assert login_body["expires_in"] == 1800
        assert login_body["user"]["username"] == "admin"
        assert login_body["user"]["role"] == "admin"
        assert login_body["user"]["is_active"] is True

        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {login_body['access_token']}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["username"] == "admin"

        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_body["refresh_token"]},
        )
        assert refresh_response.status_code == 200
        assert refresh_response.json()["token_type"] == "bearer"
        assert refresh_response.json()["access_token"]
        assert refresh_response.json()["refresh_token"]
    finally:
        app.dependency_overrides.clear()


def test_consumer_session_creates_user_with_session_id() -> None:
    session_factory = _make_session_factory()
    session_id = str(uuid4())

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        response = client.post(
            "/api/v1/auth/consumer-session", json={"session_id": session_id}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["refresh_token"]
        assert body["user"]["username"] == f"consumer-{session_id}"
        assert body["user"]["role"] == "user"
        assert body["user"]["is_active"] is True

        users_response = client.get(
            "/api/v1/users",
            headers={"Authorization": f"Bearer {body['access_token']}"},
        )
        assert users_response.status_code == 403
        assert users_response.json()["error"]["code"] == "FORBIDDEN"
    finally:
        app.dependency_overrides.clear()


def test_consumer_users_lists_active_registered_user_names() -> None:
    session_factory = _make_session_factory()
    with session_factory() as db:
        create_default_admin(db)
        alice = User(
            email="alice@example.local",
            username="alice",
            password_hash=hash_password("AlicePassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        alice.profile = UserProfile(display_name="Alice Zhang")
        disabled = User(
            email="disabled-user@example.local",
            username="disabled-user",
            password_hash=hash_password("DisabledPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.DISABLED.value,
        )
        disabled.profile = UserProfile(display_name="Disabled User")
        db.add_all([alice, disabled])
        db.commit()

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        response = client.get("/api/v1/auth/consumer-users")

        assert response.status_code == 200
        assert response.json() == {
            "items": [{"username": "alice", "display_name": "Alice Zhang"}]
        }
    finally:
        app.dependency_overrides.clear()


def test_consumer_session_returns_same_user_for_same_session_id() -> None:
    session_factory = _make_session_factory()
    session_id = str(uuid4())

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        first_response = client.post(
            "/api/v1/auth/consumer-session", json={"session_id": session_id}
        )
        assert first_response.status_code == 200
        first_user_id = first_response.json()["user"]["id"]

        second_response = client.post(
            "/api/v1/auth/consumer-session", json={"session_id": session_id}
        )
        assert second_response.status_code == 200
        assert second_response.json()["user"]["id"] == first_user_id
    finally:
        app.dependency_overrides.clear()


def test_consumer_session_creates_different_users_for_different_session_ids() -> None:
    session_factory = _make_session_factory()

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        first_response = client.post(
            "/api/v1/auth/consumer-session",
            json={"session_id": str(uuid4())},
        )
        assert first_response.status_code == 200

        second_response = client.post(
            "/api/v1/auth/consumer-session",
            json={"session_id": str(uuid4())},
        )
        assert second_response.status_code == 200
        assert (
            second_response.json()["user"]["id"]
            != first_response.json()["user"]["id"]
        )
    finally:
        app.dependency_overrides.clear()


def test_consumer_session_requires_session_id() -> None:
    session_factory = _make_session_factory()

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        response = client.post("/api/v1/auth/consumer-session", json={})

        assert response.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_logout_revokes_refresh_token() -> None:
    session_factory = _make_session_factory()
    with session_factory() as db:
        create_default_admin(db)

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "AdminPassword123"},
        )
        login_body = login_response.json()
        headers = {"Authorization": f"Bearer {login_body['access_token']}"}

        logout_response = client.post(
            "/api/v1/auth/logout",
            headers=headers,
            json={"refresh_token": login_body["refresh_token"]},
        )
        assert logout_response.status_code == 204

        refresh_response = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": login_body["refresh_token"]},
        )
        assert refresh_response.status_code == 401
        assert refresh_response.json()["error"]["code"] == "UNAUTHORIZED"

        second_logout_response = client.post(
            "/api/v1/auth/logout",
            headers=headers,
            json={"refresh_token": login_body["refresh_token"]},
        )
        assert second_logout_response.status_code == 401
        assert second_logout_response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        app.dependency_overrides.clear()


def test_logout_requires_access_token() -> None:
    session_factory = _make_session_factory()
    with session_factory() as db:
        create_default_admin(db)

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        login_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "AdminPassword123"},
        )

        response = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": login_response.json()["refresh_token"]},
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "UNAUTHORIZED"
    finally:
        app.dependency_overrides.clear()


def test_missing_access_token_returns_unauthorized_error_envelope() -> None:
    client = TestClient(app)

    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_login_failure_locks_account_after_five_attempts() -> None:
    session_factory = _make_session_factory()
    with session_factory() as db:
        create_default_admin(db)

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        for _ in range(4):
            response = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "wrong-password"},
            )
            assert response.status_code == 401
            assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"

        locked_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert locked_response.status_code == 423
        assert locked_response.json()["error"]["code"] == "ACCOUNT_LOCKED"

        still_locked_response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "AdminPassword123"},
        )
        assert still_locked_response.status_code == 423
        assert still_locked_response.json()["error"]["code"] == "ACCOUNT_LOCKED"
    finally:
        app.dependency_overrides.clear()


def test_disabled_user_cannot_login() -> None:
    session_factory = _make_session_factory()
    with session_factory() as db:
        user = User(
            email="disabled@example.local",
            username="disabled",
            password_hash=hash_password("DisabledPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.DISABLED.value,
        )
        db.add(user)
        db.commit()

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)

        response = client.post(
            "/api/v1/auth/login",
            json={"username": "disabled", "password": "DisabledPassword123"},
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "ACCOUNT_DISABLED"
    finally:
        app.dependency_overrides.clear()
