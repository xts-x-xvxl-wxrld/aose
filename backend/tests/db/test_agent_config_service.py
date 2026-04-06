from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.base import Base
from app.models import load_model_modules
from app.repositories.membership_repository import MembershipRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.agent_configs import AgentConfigService
from tests.db.helpers import get_postgres_test_urls

load_model_modules()


async def _reset_async_database(session_factory: async_sessionmaker[AsyncSession]) -> None:
    async with session_factory() as session:
        await session.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        await session.execute(text("CREATE SCHEMA public"))
        await session.commit()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
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

    async with session_factory() as session:
        yield session

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
@pytest.mark.asyncio
async def test_agent_config_service_prefers_tenant_override_then_global_then_code_default(
    db_session: AsyncSession,
) -> None:
    users = UserRepository(db_session)
    tenants = TenantRepository(db_session)
    memberships = MembershipRepository(db_session)

    actor = await users.create(
        external_auth_subject="admin-subject",
        email="admin@example.com",
        display_name="Admin",
        is_platform_admin=True,
    )
    tenant = await tenants.create(name="Tenant One", slug="tenant-one")
    other_tenant = await tenants.create(name="Tenant Two", slug="tenant-two")
    await memberships.create(tenant_id=tenant.id, user_id=actor.id, role="owner")
    await db_session.commit()

    service = AgentConfigService(db_session, settings=Settings(_env_file=None))

    global_version = await service.create_version(
        actor_user_id=actor.id,
        request_id="req-global",
        scope_type="global",
        tenant_id=None,
        payload={
            "agent_name": "account_search_agent",
            "instructions": "global override",
            "system_prompt": "global system",
            "model": "gpt-global",
            "model_settings_json": {},
            "feature_flags_json": {},
            "change_note": "global",
            "activate": True,
        },
    )
    tenant_version = await service.create_version(
        actor_user_id=actor.id,
        request_id="req-tenant",
        scope_type="tenant",
        tenant_id=tenant.id,
        payload={
            "agent_name": "account_search_agent",
            "instructions": "tenant override",
            "system_prompt": None,
            "model": "gpt-tenant",
            "model_settings_json": {},
            "feature_flags_json": {"tenant_specific": True},
            "change_note": "tenant",
            "activate": True,
        },
    )

    effective_tenant = await service.resolve_effective_config(
        tenant_id=tenant.id,
        agent_name="account_search_agent",
    )
    effective_other = await service.resolve_effective_config(
        tenant_id=other_tenant.id,
        agent_name="account_search_agent",
    )
    effective_code_default = await service.resolve_effective_config(
        tenant_id=tenant.id,
        agent_name="contact_search_agent",
    )
    snapshot = await service.build_run_config_snapshot(
        tenant_id=tenant.id,
        workflow_type="account_search",
    )

    assert global_version.status == "active"
    assert tenant_version.status == "active"
    assert effective_tenant.instructions == "tenant override"
    assert effective_tenant.model == "gpt-tenant"
    assert effective_tenant.source == "tenant_override"
    assert effective_other.instructions == "global override"
    assert effective_other.model == "gpt-global"
    assert effective_other.source == "global_override"
    assert effective_code_default.source == "code_default"
    assert snapshot["workflow_agent_name"] == "account_search_agent"
    assert snapshot["agents"]["account_search_agent"]["version_id"] == str(tenant_version.id)
