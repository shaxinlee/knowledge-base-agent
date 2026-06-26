from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    AuditLog,
    ChunkMetadata,
    File,
    KnowledgeBase,
    ParseJob,
    User,
    UserProfile,
    UserRole,
    UserStatus,
)
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


def test_admin_can_create_list_get_and_update_knowledge_base() -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        headers = {"Authorization": f"Bearer {admin_token}"}

        create_response = client.post(
            "/api/v1/knowledge-bases",
            headers=headers,
            json={"name": "Project KB", "description": "Internal docs"},
        )
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["name"] == "Project KB"
        assert created["description"] == "Internal docs"
        assert created["status"] == "active"
        assert created["file_count"] == 0
        assert created["chunk_count"] == 0

        list_response = client.get("/api/v1/knowledge-bases?keyword=Project", headers=headers)
        assert list_response.status_code == 200
        assert list_response.json()["total"] == 1
        assert list_response.json()["items"][0]["id"] == created["id"]

        get_response = client.get(f"/api/v1/knowledge-bases/{created['id']}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["id"] == created["id"]

        update_response = client.patch(
            f"/api/v1/knowledge-bases/{created['id']}",
            headers=headers,
            json={"name": "Updated KB", "description": "Updated docs", "status": "deleting"},
        )
        assert update_response.status_code == 200
        assert update_response.json()["name"] == "Updated KB"
        assert update_response.json()["description"] == "Updated docs"
        assert update_response.json()["status"] == "deleting"

        with session_factory() as db:
            audit_actions = db.scalars(select(AuditLog.action).order_by(AuditLog.created_at)).all()
        assert audit_actions == ["create_knowledge_base", "update_knowledge_base"]
    finally:
        app.dependency_overrides.clear()


def test_public_summary_does_not_require_login_and_counts_active_knowledge_bases() -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)

        empty_response = client.get("/api/v1/knowledge-bases/public-summary")
        assert empty_response.status_code == 200
        assert empty_response.json() == {"active_count": 0, "deployment_day": 1}

        admin_token = _login(client, "admin", "AdminPassword123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        client.post(
            "/api/v1/knowledge-bases",
            headers=admin_headers,
            json={"name": "Pickle Jar 1"},
        )
        deleting_response = client.post(
            "/api/v1/knowledge-bases",
            headers=admin_headers,
            json={"name": "Pickle Jar 2"},
        )
        client.patch(
            f"/api/v1/knowledge-bases/{deleting_response.json()['id']}",
            headers=admin_headers,
            json={"status": "deleting"},
        )

        summary_response = client.get("/api/v1/knowledge-bases/public-summary")
        assert summary_response.status_code == 200
        payload = summary_response.json()
        assert payload["active_count"] == 1
        assert payload["deployment_day"] >= 1
    finally:
        app.dependency_overrides.clear()


def test_user_can_only_read_active_knowledge_bases() -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        user_token = _login(client, "reader", "ReaderPassword123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        user_headers = {"Authorization": f"Bearer {user_token}"}

        active_response = client.post(
            "/api/v1/knowledge-bases",
            headers=admin_headers,
            json={"name": "Visible KB"},
        )
        deleting_response = client.post(
            "/api/v1/knowledge-bases",
            headers=admin_headers,
            json={"name": "Hidden KB"},
        )
        client.patch(
            f"/api/v1/knowledge-bases/{deleting_response.json()['id']}",
            headers=admin_headers,
            json={"status": "deleting"},
        )

        list_response = client.get("/api/v1/knowledge-bases", headers=user_headers)
        assert list_response.status_code == 200
        items = list_response.json()["items"]
        assert [item["id"] for item in items] == [active_response.json()["id"]]

        forbidden_create = client.post(
            "/api/v1/knowledge-bases",
            headers=user_headers,
            json={"name": "Forbidden KB"},
        )
        assert forbidden_create.status_code == 403
        assert forbidden_create.json()["error"]["code"] == "FORBIDDEN"

        hidden_get = client.get(
            f"/api/v1/knowledge-bases/{deleting_response.json()['id']}",
            headers=user_headers,
        )
        assert hidden_get.status_code == 404
        assert hidden_get.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    finally:
        app.dependency_overrides.clear()


def test_knowledge_base_list_returns_real_file_and_active_chunk_counts() -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        headers = {"Authorization": f"Bearer {admin_token}"}

        create_response = client.post(
            "/api/v1/knowledge-bases",
            headers=headers,
            json={"name": "Indexed KB"},
        )
        knowledge_base_id = UUID(create_response.json()["id"])

        with session_factory() as db:
            admin = db.scalar(select(User).where(User.username == "admin"))
            assert admin is not None
            file = File(
                knowledge_base_id=knowledge_base_id,
                file_name="manual.pdf",
                file_ext=".pdf",
                mime_type="application/pdf",
                file_size=100,
                file_hash="a" * 64,
                storage_bucket="raw-files",
                storage_key="manual.pdf",
                status="indexed",
                created_by=admin.id,
            )
            db.add(file)
            db.flush()
            parse_job = ParseJob(
                file_id=file.id,
                knowledge_base_id=knowledge_base_id,
                status="indexed",
                progress=100,
                created_by=admin.id,
            )
            db.add(parse_job)
            db.flush()
            file.latest_parse_job_id = parse_job.id
            db.add_all(
                [
                    ChunkMetadata(
                        knowledge_base_id=knowledge_base_id,
                        file_id=file.id,
                        parse_job_id=parse_job.id,
                        chunk_index=0,
                        content="active chunk",
                        content_hash="b" * 64,
                        token_count=2,
                        source_type="pdf",
                        source_locator="pdf:p1",
                        is_active=True,
                    ),
                    ChunkMetadata(
                        knowledge_base_id=knowledge_base_id,
                        file_id=file.id,
                        parse_job_id=parse_job.id,
                        chunk_index=1,
                        content="inactive chunk",
                        content_hash="c" * 64,
                        token_count=2,
                        source_type="pdf",
                        source_locator="pdf:p2",
                        is_active=False,
                    ),
                ]
            )
            db.commit()

        list_response = client.get("/api/v1/knowledge-bases?keyword=Indexed", headers=headers)
        assert list_response.status_code == 200
        item = list_response.json()["items"][0]
        assert item["file_count"] == 1
        assert item["chunk_count"] == 1

        get_response = client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}", headers=headers)
        assert get_response.status_code == 200
        assert get_response.json()["file_count"] == 1
        assert get_response.json()["chunk_count"] == 1
    finally:
        app.dependency_overrides.clear()


def test_admin_delete_soft_deletes_and_writes_audit_log() -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        headers = {"Authorization": f"Bearer {admin_token}"}

        create_response = client.post(
            "/api/v1/knowledge-bases",
            headers=headers,
            json={"name": "Delete Me"},
        )
        knowledge_base_id = create_response.json()["id"]
        knowledge_base_uuid = UUID(knowledge_base_id)

        delete_response = client.delete(
            f"/api/v1/knowledge-bases/{knowledge_base_id}", headers=headers
        )
        assert delete_response.status_code == 204

        default_list_response = client.get("/api/v1/knowledge-bases", headers=headers)
        assert default_list_response.status_code == 200
        assert default_list_response.json()["total"] == 0

        deleted_list_response = client.get(
            "/api/v1/knowledge-bases?status=deleted", headers=headers
        )
        assert deleted_list_response.status_code == 200
        assert deleted_list_response.json()["total"] == 1

        with session_factory() as db:
            knowledge_base = db.get(KnowledgeBase, knowledge_base_uuid)
            audit_log = db.scalar(
                select(AuditLog).where(
                    AuditLog.action == "delete_knowledge_base",
                    AuditLog.resource_id == knowledge_base_uuid,
                )
            )
        assert knowledge_base is not None
        assert knowledge_base.status == "deleted"
        assert knowledge_base.deleted_at is not None
        assert audit_log is not None
        assert audit_log.details is not None
        assert audit_log.details["before"]["name"] == "Delete Me"
    finally:
        app.dependency_overrides.clear()


def test_admin_can_list_audit_logs_and_user_is_forbidden() -> None:
    session_factory = _make_session_factory()
    _seed_admin_and_user(session_factory)
    _install_db_override(session_factory)
    try:
        client = TestClient(app)
        admin_token = _login(client, "admin", "AdminPassword123")
        user_token = _login(client, "reader", "ReaderPassword123")
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        user_headers = {"Authorization": f"Bearer {user_token}"}

        create_response = client.post(
            "/api/v1/knowledge-bases",
            headers=admin_headers,
            json={"name": "Audited KB"},
        )
        client.delete(
            f"/api/v1/knowledge-bases/{create_response.json()['id']}", headers=admin_headers
        )

        user_response = client.get("/api/v1/audit-logs", headers=user_headers)
        assert user_response.status_code == 403
        assert user_response.json()["error"]["code"] == "FORBIDDEN"

        admin_response = client.get(
            "/api/v1/audit-logs?action=delete_knowledge_base&resource_type=knowledge_base",
            headers=admin_headers,
        )
        assert admin_response.status_code == 200
        body = admin_response.json()
        assert body["total"] == 1
        assert body["items"][0]["action"] == "delete_knowledge_base"
        assert body["items"][0]["resource_type"] == "knowledge_base"
        assert body["items"][0]["resource_id"] == create_response.json()["id"]
    finally:
        app.dependency_overrides.clear()
