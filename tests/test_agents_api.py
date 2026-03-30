from fastapi.testclient import TestClient

from app.main import create_app


def test_agent_system_blueprint_exposes_expected_agents() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/agents")

    assert response.status_code == 200
    body = response.json()
    names = [agent["name"] for agent in body["agents"]]
    assert names == [
        "orchestrator_agent",
        "account_search_agent",
        "account_research_agent",
        "contact_search_agent",
    ]
    assert body["agents"][0]["handoffs"] == [
        "account_search_agent",
        "account_research_agent",
        "contact_search_agent",
    ]
