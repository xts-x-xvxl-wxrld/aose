# Developer Golden Path

This runbook outlines the required lifecycle operations for local development.

## Windows boundary rule
- **Worker execution and worker tests run in Linux container only.**
- Windows host runs wrapper scripts + browser calls only.
- Importing worker modules on the Windows host may fail due to `rq` forking logic.

## Commands (Windows PowerShell)

Use the provided wrapper script from the repository root:

- **up**: `.\scripts\dev.ps1 up`
- **down**: `.\scripts\dev.ps1 down`
- **ps/status**: `.\scripts\dev.ps1 ps`
- **logs**: `.\scripts\dev.ps1 logs`
- **health check (host call)**: `.\scripts\dev.ps1 health` (Calls `http://localhost:8000/healthz` from host)
- **health check (container call, optional)**: `docker compose exec api curl -s http://localhost:8000/healthz`
- **migrations**: `.\scripts\dev.ps1 migrate` (Executes inside `api` container)
- **tests + lint**: `.\scripts\dev.ps1 test` and `.\scripts\dev.ps1 lint` (Executes inside containers)

## Commands (Bash / Linux / macOS)

Use the provided wrapper script from the repository root:

- **up**: `./scripts/dev.sh up`
- **down**: `./scripts/dev.sh down`
- **ps/status**: `./scripts/dev.sh ps`
- **logs**: `./scripts/dev.sh logs`
- **health check (host call)**: `./scripts/dev.sh health`
- **health check (container call, optional)**: `docker compose exec api curl -s http://localhost:8000/healthz`
- **migrations**: `./scripts/dev.sh migrate` (Executes inside `api` container)
- **tests + lint**: `./scripts/dev.sh test` and `./scripts/dev.sh lint` (Executes inside containers)
