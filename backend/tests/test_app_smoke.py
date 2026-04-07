from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_bootstraps_agent_system_and_current_routes() -> None:
    app = create_app()

    assert app.title == "Agentic OSE"
    assert app.state.agent_system.orchestrator.name == "orchestrator_agent"
    assert app.state.workflow_executor is not None

    paths = {route.path for route in app.routes}

    assert "/api/v1/healthz" in paths
    assert "/api/v1/agents" in paths
    assert "/api/v1/tenants" in paths
    assert "/api/v1/tenants/{tenant_id}/members" in paths
    assert "/api/v1/tenants/{tenant_id}/members/{membership_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/members/{membership_id}/transfer-ownership" in paths
    assert "/api/v1/tenants/{tenant_id}/chat/stream" in paths
    assert "/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages" in paths
    assert "/api/v1/tenants/{tenant_id}/seller-profiles" in paths
    assert "/api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/icp-profiles" in paths
    assert "/api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/accounts" in paths
    assert "/api/v1/tenants/{tenant_id}/accounts/{account_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/contacts" in paths
    assert "/api/v1/tenants/{tenant_id}/contacts/{contact_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/workflow-runs" in paths
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence" in paths
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/debug" in paths
    assert "/api/v1/tenants/{tenant_id}/artifacts/{artifact_id}" in paths
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals" in paths


def test_openapi_smoke_exposes_current_public_routes() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    assert "/api/v1/healthz" in schema["paths"]
    assert "/api/v1/agents" in schema["paths"]
    assert "/api/v1/tenants" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/members" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/members/{membership_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/chat/stream" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages" in schema["paths"]
    assert (
        "/api/v1/tenants/{tenant_id}/members/{membership_id}/transfer-ownership"
        in schema["paths"]
    )
    assert "/api/v1/tenants/{tenant_id}/seller-profiles" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/icp-profiles" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/accounts" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/accounts/{account_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/contacts" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/contacts/{contact_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/workflow-runs" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/debug" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/artifacts/{artifact_id}" in schema["paths"]
    assert "/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/healthz"]
    assert "get" in schema["paths"]["/api/v1/agents"]
    assert "post" in schema["paths"]["/api/v1/tenants"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/members"]
    assert "post" in schema["paths"]["/api/v1/tenants/{tenant_id}/members"]
    assert "patch" in schema["paths"]["/api/v1/tenants/{tenant_id}/members/{membership_id}"]
    assert "delete" in schema["paths"]["/api/v1/tenants/{tenant_id}/members/{membership_id}"]
    assert "post" in schema["paths"]["/api/v1/tenants/{tenant_id}/chat/stream"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/chat/threads/{thread_id}/messages"]
    assert "post" in schema["paths"]["/api/v1/tenants/{tenant_id}/seller-profiles"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/seller-profiles"]
    assert (
        "patch"
        in schema["paths"]["/api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}"]
    )
    assert (
        "get"
        in schema["paths"]["/api/v1/tenants/{tenant_id}/seller-profiles/{seller_profile_id}"]
    )
    assert "post" in schema["paths"]["/api/v1/tenants/{tenant_id}/icp-profiles"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/icp-profiles"]
    assert "patch" in schema["paths"]["/api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/icp-profiles/{icp_profile_id}"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/accounts"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/accounts/{account_id}"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/contacts"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/contacts/{contact_id}"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/workflow-runs"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/evidence"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/debug"]
    assert "get" in schema["paths"]["/api/v1/tenants/{tenant_id}/artifacts/{artifact_id}"]
    assert "post" in schema["paths"]["/api/v1/tenants/{tenant_id}/workflow-runs/{run_id}/approvals"]
    assert (
        "post"
        in schema["paths"][
            "/api/v1/tenants/{tenant_id}/members/{membership_id}/transfer-ownership"
        ]
    )
