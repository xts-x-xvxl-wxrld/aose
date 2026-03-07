# api/AGENT.md — FastAPI Service

## Purpose

The API service exposes REST endpoints, owns the Postgres connection, and manages DB schema via Alembic. In the organ pipeline it is the entry point for external requests and the admin surface for reviewing pipeline state.

## Entry points

| File | Role |
|------|------|
| `api/aose_api/main.py` | FastAPI app instance, all route definitions |
| `api/migrations/env.py` | Alembic migration environment |
| `api/alembic.ini` | Alembic config (points at `migrations/`) |

## Routes (current)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/healthz` | Liveness + Postgres connectivity check. Returns `{"status": "ok", "env": "<APP_ENV>"}` or 503. |

## Configuration (env vars)

Read via `os.getenv` or `pydantic-settings`. Source from `.env` locally; injected by Docker Compose in containers.

| Variable | Default | Used for |
|----------|---------|---------|
| `DATABASE_URL` | _(required)_ | psycopg DSN (`postgresql+psycopg://...`) |
| `APP_ENV` | `local` | Tag returned in health check |
| `API_HOST` | `0.0.0.0` | uvicorn bind address |
| `API_PORT` | `8000` | uvicorn bind port |

## Database access

- Driver: `psycopg` (v3, binary) for raw connections; `sqlalchemy` v2 for ORM use
- Migrations: Alembic — add new migrations with `make db-migrate`
- Current schema: empty (no tables yet — Epic B adds the Data Spine tables)

## Testing

```
api/tests/
├── test_api.py          # Health endpoint test (monkeypatches DATABASE_URL)
└── test_invariants.py   # Skipped gate for PH-004 (schema/replay/budget/send invariants)
```

Run tests: `make test` (runs inside the api container via `docker compose run --rm`).

Pattern for new endpoint tests:
```python
from fastapi.testclient import TestClient
from aose_api.main import app

client = TestClient(app)

def test_my_endpoint(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    response = client.get("/my-endpoint")
    assert response.status_code == 200
```

## Adding a new route

1. Define the handler in `api/aose_api/main.py` (or a new router module imported there).
2. Add a test in `api/tests/`.
3. If the route needs a new DB table: add an Alembic migration (`make db-migrate`).
4. Every handler must emit a `StructuredEvent` — see `docs/data-spine/DATA-SPINE-v0.1.md` §4.10.

## Dev commands

```bash
make dev          # Start full stack including this service (port 8000)
make test         # Run api tests in container
make lint         # Ruff lint api/
make fmt          # Ruff format api/
make db-migrate   # Run pending Alembic migrations
```

## CI behaviour

CI (`python-checks` job in `.github/workflows/ci.yml`) runs:
1. `ruff format --check api/ worker/`
2. `ruff check api/ worker/`
3. `pytest api/ worker/`
4. Grep for `PH-004` in `test_invariants.py` skip reason (invariant gate)
