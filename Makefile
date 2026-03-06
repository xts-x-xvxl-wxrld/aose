.PHONY: up down dev logs test lint fmt fmt-check db-migrate

up:
	docker compose up -d postgres redis

down:
	docker compose down -v

dev:
	docker compose up -d --build postgres redis api worker

logs:
	docker compose logs -f --tail=200 api worker postgres redis

test:
	docker compose run --rm api pytest -q
	docker compose run --rm worker pytest -q

lint:
	docker compose run --rm api ruff check .
	docker compose run --rm worker ruff check .

fmt:
	docker compose run --rm api ruff format .
	docker compose run --rm worker ruff format .

fmt-check:
	docker compose run --rm api ruff format --check .
	docker compose run --rm worker ruff format --check .

db-migrate:
	docker compose run --rm api alembic upgrade head
