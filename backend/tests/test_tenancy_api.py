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

    await _reset_async_database(session_factory)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    yield engine
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_tenant_creation_and_member_listing_flow(db_engine: AsyncEngine) -> None:
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
            create_response = await client.post(
                "/api/v1/tenants",
                json={"name": "Acme Workspace", "slug": "Acme Workspace"},
            )
            assert create_response.status_code == 201
            create_body = create_response.json()
            assert create_body["name"] == "Acme Workspace"
            assert create_body["slug"] == "acme-workspace"
            assert create_body["creator_role"] == "owner"
            assert create_body["creator_status"] == "active"

            tenants_response = await client.get("/api/v1/tenants")
            assert tenants_response.status_code == 200
            tenants_body = tenants_response.json()
            assert tenants_body["tenants"] == [
                {
                    "tenant_id": create_body["tenant_id"],
                    "tenant_name": "Acme Workspace",
                    "role": "owner",
                    "status": "active",
                }
            ]

            members_response = await client.get(
                f"/api/v1/tenants/{create_body['tenant_id']}/members"
            )
            assert members_response.status_code == 200
            members_body = members_response.json()
            assert len(members_body["members"]) == 1
            assert (
                members_body["members"][0]["membership_id"]
                == create_body["creator_membership_id"]
            )
            assert members_body["members"][0]["role"] == "owner"
            assert members_body["members"][0]["status"] == "active"
    finally:
        app.dependency_overrides.clear()
