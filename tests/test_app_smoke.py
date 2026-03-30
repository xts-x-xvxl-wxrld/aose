from fastapi.testclient import TestClient

from app.main import create_app


def test_create_app_bootstraps_agent_system_and_current_routes() -> None:
    app = create_app()

    assert app.title == "Agentic OSE"
    assert app.state.agent_system.orchestrator.name == "orchestrator_agent"

    paths = {route.path for route in app.routes}

    assert "/api/v1/healthz" in paths
    assert "/api/v1/agents" in paths


def test_openapi_smoke_exposes_current_public_routes() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200

    schema = response.json()

    assert "/api/v1/healthz" in schema["paths"]
    assert "/api/v1/agents" in schema["paths"]
    assert "get" in schema["paths"]["/api/v1/healthz"]
    assert "get" in schema["paths"]["/api/v1/agents"]

