from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db_session, get_optional_db_session
from app.main import create_app
from app.models import load_model_modules
from tests.db.helpers import get_postgres_test_urls

load_model_modules()


async def _reset_async_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await session.execute(text("CREATE SCHEMA public"))
        await session.commit()


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    async_url, _sync_url = get_postgres_test_urls()
    engine = create_async_engine(async_url)
    session_factory = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    try:
        await _reset_async_database(session_factory)
    except Exception as exc:  # pragma: no cover - environment-dependent skip
        await engine.dispose()
        pytest.skip(f"Postgres-backed DB tests are unavailable in this environment: {exc}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_admin_endpoints_expose_platform_and_tenant_scope(db_engine: AsyncEngine) -> None:
    app = create_app()
    session_factory = async_sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = override_get_db_session
    app.dependency_overrides[get_optional_db_session] = override_get_db_session

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            me_response = await client.get("/api/v1/me")
            assert me_response.status_code == 200
            assert me_response.json()["is_platform_admin"] is True

            create_tenant_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Admin Tenant", "slug": "admin-tenant"},
            )
            assert create_tenant_response.status_code == 201
            tenant_id = create_tenant_response.json()["tenant_id"]

            overview_response = await client.get("/api/v1/admin/overview")
            assert overview_response.status_code == 200
            assert overview_response.json()["total_tenants"] == 1

            create_config_response = await client.post(
                f"/api/v1/admin/tenants/{tenant_id}/agent-configs/versions",
                json={
                    "agent_name": "account_search_agent",
                    "instructions": "tenant override",
                    "model": "gpt-tenant",
                    "change_note": "tenant test",
                    "activate": True,
                },
            )
            assert create_config_response.status_code == 201
            version_id = create_config_response.json()["id"]

            tenant_configs_response = await client.get(
                f"/api/v1/admin/tenants/{tenant_id}/agent-configs"
            )
            assert tenant_configs_response.status_code == 200
            account_search_config = next(
                config
                for config in tenant_configs_response.json()["configs"]
                if config["agent_name"] == "account_search_agent"
            )
            assert account_search_config["tenant_active"]["id"] == version_id
            assert account_search_config["effective"]["model"] == "gpt-tenant"
    finally:
        app.dependency_overrides.clear()
