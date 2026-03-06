#!/usr/bin/env bash
set -euo pipefail

# Determine compose file automatically
if [ -f "compose.yaml" ]; then
    COMPOSE_FILE="compose.yaml"
elif [ -f "docker-compose.yml" ]; then
    COMPOSE_FILE="docker-compose.yml"
else
    echo "Error: No docker-compose file found."
    exit 1
fi

echo "Starting Docker Compose stack using $COMPOSE_FILE..."
docker compose -f "$COMPOSE_FILE" up -d --build

echo "Waiting for API health at http://localhost:8000/healthz..."
MAX_RETRIES=30
RETRY_COUNT=0
HEALTH_OK=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if curl -s http://localhost:8000/healthz | grep -q '"status":"ok"'; then
        HEALTH_OK=true
        echo "API is healthy!"
        break
    fi
    echo "Waiting... (Attempt $((RETRY_COUNT+1))/$MAX_RETRIES)"
    sleep 2
    RETRY_COUNT=$((RETRY_COUNT+1))
done

if [ "$HEALTH_OK" = false ]; then
    echo "Error: API failed healthcheck."
    exit 1
fi

echo "Running verification commands..."
HAS_ERRORS=0

if [ -f "Makefile" ] && grep -q "lint:" Makefile && grep -q "fmt-check:" Makefile && grep -q "test:" Makefile; then
    echo "Makefile detected with targets. Running via make targets..."
    # Execute underlying commands from Makefile if required, or simply execute the targets directly if make exists
    # Assuming make is NOT available, but Makefile targets are inside container commands:
    # Actually, the instructions say: 
    # "Read Makefile if present; if it has targets for lint/fmt-check/test, execute their underlying commands in the right service container."
    # "If Makefile parsing is too heavy, fall back to these canonical commands inside containers:"
    # We will fall back to canonical commands as it's more robust than parsing Makefiles in bash.
    echo "Falling back to canonical commands..."
fi

# Canonical commands
if ! docker compose exec -T api python -m ruff check . || ! docker compose exec -T worker python -m ruff check .; then
    echo "Lint failed"
    HAS_ERRORS=1
fi

if ! docker compose exec -T api python -m ruff format --check . || ! docker compose exec -T worker python -m ruff format --check .; then
    echo "Format check failed"
    HAS_ERRORS=1
fi

if ! docker compose exec -T api python -m pytest -q || ! docker compose exec -T worker python -m pytest -q; then
    echo "Tests failed"
    HAS_ERRORS=1
fi

if [ $HAS_ERRORS -eq 0 ]; then
    echo "Verification Passed."
else
    echo "Verification Failed."
    exit 1
fi
