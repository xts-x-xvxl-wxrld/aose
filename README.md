# Agentic OSE Backend

Minimal FastAPI backend skeleton for an agentic SaaS.

## Python Version

Use Python `3.12.10` for local development and CI.

## Bootstrap

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -e .[dev]
```

## What is in the skeleton

- FastAPI application factory
- Versioned API router
- Health endpoint
- Settings loader
- Agent skeleton with an orchestrator and specialist agents
- Agent registry inspection endpoint
- Basic API test

## Run locally

```bash
uvicorn app.main:app --app-dir src --reload
```

## Run with Docker

1. Optionally create a local `.env` file from `.env.example` if you want to override defaults.
2. Start the API and Postgres containers:

```bash
docker compose up --build
```

The API will be available at `http://localhost:8000` and Postgres will be available on `localhost:5432`.

Current note:

- the Docker stack already provisions Postgres and passes `DATABASE_URL` into the app container
- the current backend skeleton does not use the database yet, but the container setup is ready for the upcoming persistence work

Current Docker services:

- `api`
  Runs the FastAPI backend with `uvicorn`
- `postgres`
  Runs PostgreSQL 16 with a persistent named volume

Useful commands:

```bash
docker compose up --build -d
docker compose logs -f api
docker compose down
```

## Tooling

```bash
ruff check .
mypy src
pytest -q
alembic upgrade head
```

## Run tests

```bash
pytest -q
```

## Main endpoints

- `GET /api/v1/healthz`
- `GET /api/v1/agents`
