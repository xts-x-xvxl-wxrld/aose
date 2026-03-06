#!/usr/bin/env bash

set -e

COMMAND=$1

cd "$(dirname "$0")/.."

case "$COMMAND" in
    up)
        docker compose up -d
        ;;
    down)
        docker compose down -v
        ;;
    ps)
        docker compose ps
        ;;
    logs)
        docker compose logs -f
        ;;
    health)
        curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/healthz
        ;;
    migrate)
        docker compose exec api alembic upgrade head
        ;;
    test)
        echo "Running tests in container per Windows boundary rule..."
        docker compose exec api pytest -q .
        docker compose exec worker pytest -q .
        ;;
    lint)
        echo "Running linting in container per Windows boundary rule..."
        docker compose exec api ruff check .
        docker compose exec api ruff format --check .
        docker compose exec worker ruff check .
        docker compose exec worker ruff format --check .
        ;;
    *)
        echo "Usage: $0 {up|down|ps|logs|health|migrate|test|lint}"
        exit 1
        ;;
esac
