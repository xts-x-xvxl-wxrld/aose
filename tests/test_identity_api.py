from fastapi.testclient import TestClient

from app.db.session import get_optional_db_session
from app.main import create_app


def test_me_endpoint_uses_fake_auth_request_context() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    client = TestClient(app)

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user_dev"
    assert body["external_auth_subject"] == "dev-user"
    assert body["email"] == "dev@agentic-ose.local"
    assert "request_id" in body


def test_tenants_endpoint_returns_fake_membership() -> None:
    app = create_app()

    async def override_get_optional_db_session():
        yield None

    app.dependency_overrides[get_optional_db_session] = override_get_optional_db_session
    client = TestClient(app)

    response = client.get("/api/v1/tenants")

    assert response.status_code == 200
    body = response.json()
    assert body["tenants"] == [
        {
            "tenant_id": "tenant_dev",
            "tenant_name": "Local Dev Tenant",
            "role": "owner",
            "status": "active",
        }
    ]
