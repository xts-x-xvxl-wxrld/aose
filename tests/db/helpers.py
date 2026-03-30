from __future__ import annotations

import os

import pytest


def get_postgres_test_urls() -> tuple[str, str]:
    raw_url = os.getenv("TEST_DATABASE_URL")
    if not raw_url:
        pytest.skip("TEST_DATABASE_URL is not configured for Postgres-backed DB tests.")

    if raw_url.startswith("postgresql+asyncpg://"):
        async_url = raw_url
        sync_url = raw_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif raw_url.startswith("postgresql+psycopg://"):
        async_url = raw_url
        sync_url = raw_url
    elif raw_url.startswith("postgresql://"):
        async_url = raw_url.replace("postgresql://", "postgresql+psycopg://", 1)
        sync_url = async_url
    else:
        raise RuntimeError("TEST_DATABASE_URL must be a PostgreSQL URL.")

    return async_url, sync_url
