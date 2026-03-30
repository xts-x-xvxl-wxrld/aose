from fastapi.testclient import TestClient

from app.main import create_app


def test_me_endpoint_uses_fake_auth_request_context() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/me")

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "user_dev"
    assert body["external_auth_subject"] == "dev-user"
    assert body["email"] == "dev@agentic-ose.local"
    assert "request_id" in body


def test_tenants_endpoint_returns_fake_membership() -> None:
    client = TestClient(create_app())

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
