# Agentic OSE Workspace

This repository now has a clearer split between the two applications and the root workspace that orchestrates them.

## Layout

- `backend/`: FastAPI app, database models, migrations, tests, and backend packaging
- `frontend/`: React/Vite app for the workspace UI
- `docs/`: shared project notes and integration maps
- `resources/`: supporting assets and reference material
- `docker-compose.yml`: root dev orchestration for backend, frontend, and Postgres

## Local development

### Full workspace

1. Copy `.env.example` to `.env` at the repo root.
2. Run `docker compose up --build`.
3. Open `http://localhost:5173`.

### Backend only

1. Copy `backend/.env.example` to `backend/.env` if you want a backend-local env file.
2. Work from `backend/` for API, migrations, and tests.

### Frontend only

1. Copy `frontend/.env.example` to `frontend/.env.local` if needed.
2. Run the frontend from `frontend/`.

## Notes

- The root `.env` is the shared default for Docker Compose.
- The backend also supports a local `backend/.env` when run directly from the `backend/` directory.
- The frontend proxies API requests to the backend and now targets `/api/v1`.
