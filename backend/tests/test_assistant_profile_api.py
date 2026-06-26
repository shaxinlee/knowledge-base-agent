from collections.abc import Generator
import json

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
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


def _seed_admin_and_user(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as db:
        create_default_admin(db)
        user = User(
            email="reader@example.local",
            username="reader",
            password_hash=hash_password("ReaderPassword123"),
            role=UserRole.USER.value,
            status=UserStatus.ACTIVE.value,
        )
        user.profile = UserProfile(display_name="Reader")
        db.add(user)
        db.commit()


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return str(response.json()["access_token"])


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_admin_can_read_and_update_assistant_profile(tmp_path) -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    settings = get_settings()
    original_path = settings.assistant_profile_config_path
    settings.assistant_profile_config_path = str(tmp_path / "assistant_profile.json")

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")

        read_response = client.get("/api/v1/assistant-profile", headers=_headers(admin_token))
        assert read_response.status_code == 200
        payload = read_response.json()
        assert payload["name"] == "知识库问答助手"

        payload["name"] = "内部资料助手"
        payload["identity_answer"] = "我是内部资料助手。"
        update_response = client.patch(
            "/api/v1/assistant-profile",
            headers=_headers(admin_token),
            json=payload,
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "内部资料助手"

        reread_response = client.get("/api/v1/assistant-profile", headers=_headers(admin_token))
        assert reread_response.status_code == 200
        assert reread_response.json()["identity_answer"] == "我是内部资料助手。"
    finally:
        settings.assistant_profile_config_path = original_path
        app.dependency_overrides.clear()


def test_non_admin_cannot_update_assistant_profile(tmp_path) -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    settings = get_settings()
    original_path = settings.assistant_profile_config_path
    settings.assistant_profile_config_path = str(tmp_path / "assistant_profile.json")

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        user_token = _login(client, "reader", "ReaderPassword123")
        response = client.patch(
            "/api/v1/assistant-profile",
            headers=_headers(user_token),
            json={
                "name": "内部资料助手",
                "identity_answer": "我是内部资料助手。",
                "capability_answer": "我可以查询资料。",
                "greeting_answer": "你好。",
                "thanks_answer": "不客气。",
                "usage_answer": "直接提问即可。",
                "handoff_answer": "请联系管理员。",
                "fallback_casual_answer": "我更适合回答资料问题。",
            },
        )
        assert response.status_code == 403
    finally:
        settings.assistant_profile_config_path = original_path
        app.dependency_overrides.clear()


def test_admin_can_read_and_update_model_settings(tmp_path) -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    settings = get_settings()
    original_path = settings.model_settings_config_path
    config_path = tmp_path / "model_settings.json"
    settings.model_settings_config_path = str(config_path)

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")

        read_response = client.get("/api/v1/model-settings", headers=_headers(admin_token))
        assert read_response.status_code == 200
        payload = read_response.json()
        assert payload["text_embedding"]["model"] == "bge-m3"
        assert payload["reranker"]["model"] == "bge-reranker"

        payload["llm"] = {
            "base_url": "https://llm.example.test/v1",
            "api_key": "test-llm-key",
            "model": "qwen-test",
        }
        payload["text_embedding"] = {
            "base_url": "https://embedding.example.test/v1",
            "api_key": "test-embedding-key",
            "model": "bge-m3-test",
        }
        update_response = client.patch(
            "/api/v1/model-settings",
            headers=_headers(admin_token),
            json=payload,
        )
        assert update_response.status_code == 200
        assert update_response.json()["llm"]["model"] == "qwen-test"

        saved_payload = json.loads(config_path.read_text(encoding="utf-8"))
        assert saved_payload["llm"]["api_key"] == "test-llm-key"
        assert saved_payload["text_embedding"]["base_url"] == "https://embedding.example.test/v1"
    finally:
        settings.model_settings_config_path = original_path
        app.dependency_overrides.clear()


def test_non_admin_cannot_update_model_settings(tmp_path) -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    settings = get_settings()
    original_path = settings.model_settings_config_path
    settings.model_settings_config_path = str(tmp_path / "model_settings.json")

    def override_db() -> Generator[Session, None, None]:
        yield from _override_db(session_factory)

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        user_token = _login(client, "reader", "ReaderPassword123")
        response = client.patch(
            "/api/v1/model-settings",
            headers=_headers(user_token),
            json={
                "mineru": {"base_url": "", "api_key": "", "model": ""},
                "llm": {"base_url": "", "api_key": "", "model": ""},
                "text_embedding": {"base_url": "", "api_key": "", "model": ""},
                "reranker": {"base_url": "", "api_key": "", "model": ""},
                "intent_recognition": {"base_url": "", "api_key": "", "model": ""},
                "knowledge_search_classifier": {"base_url": "", "api_key": "", "model": ""},
                "image_description": {"base_url": "", "api_key": "", "model": ""},
                "multimodal_embedding": {"base_url": "", "api_key": "", "model": ""},
            },
        )
        assert response.status_code == 403
    finally:
        settings.model_settings_config_path = original_path
        app.dependency_overrides.clear()
