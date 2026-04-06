# ICP Search Frontend

React 18 + Vite frontend for the Agentic OSE workspace.

## Local development

1. Copy `frontend/.env.example` to `frontend/.env.local` if you want to override defaults.
2. Run `npm install`.
3. Run `npm run dev`.

The app uses `/api/v1` by default and proxies requests to `http://localhost:8000`.

## Docker Compose

`docker compose up --build` now starts:

- `postgres` on `5432`
- `api` on `8000`
- `frontend` on `5173`

The frontend service waits for the backend health endpoint at `/api/v1/healthz` before starting Vite.
