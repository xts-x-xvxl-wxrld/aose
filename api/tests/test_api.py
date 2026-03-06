from fastapi.testclient import TestClient
from aose_api.main import app

client = TestClient(app)


def test_read_healthz(monkeypatch):
    # Ensure DATABASE_URL is not set so we bypass real DB check for unit tests
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
