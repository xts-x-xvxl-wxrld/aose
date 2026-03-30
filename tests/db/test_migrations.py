from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from .helpers import get_postgres_test_urls


def _reset_database(sync_url: str) -> None:
    engine = create_engine(sync_url)
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _alembic_config(sync_url: str) -> Config:
    config = Config(str(Path("alembic.ini").resolve()))
    config.set_main_option("sqlalchemy.url", sync_url)
    return config


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
def test_migration_upgrade_creates_phase_1_tables() -> None:
    _async_url, sync_url = get_postgres_test_urls()
    _reset_database(sync_url)

    config = _alembic_config(sync_url)
    command.upgrade(config, "head")

    engine = create_engine(sync_url)
    inspector = inspect(engine)

    assert {
        "users",
        "tenants",
        "tenant_memberships",
        "seller_profiles",
        "icp_profiles",
        "conversation_threads",
        "conversation_messages",
        "workflow_runs",
        "run_events",
        "accounts",
        "account_research_snapshots",
        "contacts",
        "source_evidence",
        "artifacts",
        "approval_decisions",
    } <= set(inspector.get_table_names())

    user_unique_columns = {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("users")}
    tenant_unique_columns = {tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("tenants")}
    membership_unique_columns = {
        tuple(constraint["column_names"]) for constraint in inspector.get_unique_constraints("tenant_memberships")
    }
    assert ("external_auth_subject",) in user_unique_columns
    assert ("slug",) in tenant_unique_columns
    assert ("tenant_id", "user_id") in membership_unique_columns

    thread_indexes = {index["name"] for index in inspector.get_indexes("conversation_threads")}
    message_indexes = {index["name"] for index in inspector.get_indexes("conversation_messages")}
    workflow_run_indexes = {index["name"] for index in inspector.get_indexes("workflow_runs")}
    run_event_indexes = {index["name"] for index in inspector.get_indexes("run_events")}
    account_indexes = {index["name"] for index in inspector.get_indexes("accounts")}
    snapshot_indexes = {index["name"] for index in inspector.get_indexes("account_research_snapshots")}
    contact_indexes = {index["name"] for index in inspector.get_indexes("contacts")}
    evidence_indexes = {index["name"] for index in inspector.get_indexes("source_evidence")}
    artifact_indexes = {index["name"] for index in inspector.get_indexes("artifacts")}
    approval_indexes = {index["name"] for index in inspector.get_indexes("approval_decisions")}

    assert "ix_conversation_threads_tenant_id" in thread_indexes
    assert "ix_conversation_threads_seller_profile_id" in thread_indexes
    assert "ix_conversation_messages_tenant_id" in message_indexes
    assert "ix_conversation_messages_thread_id" in message_indexes
    assert "ix_conversation_messages_run_id" in message_indexes
    assert "ix_workflow_runs_tenant_id" in workflow_run_indexes
    assert "ix_workflow_runs_thread_id" in workflow_run_indexes
    assert "uq_workflow_runs_tenant_correlation_id" in workflow_run_indexes
    assert "ix_run_events_tenant_id" in run_event_indexes
    assert "ix_run_events_run_id" in run_event_indexes
    assert "ix_accounts_tenant_id" in account_indexes
    assert "ix_accounts_source_workflow_run_id" in account_indexes
    assert "uq_accounts_tenant_normalized_domain" in account_indexes
    assert "ix_account_research_snapshots_tenant_id" in snapshot_indexes
    assert "ix_account_research_snapshots_account_id" in snapshot_indexes
    assert "ix_account_research_snapshots_workflow_run_id" in snapshot_indexes
    assert "ix_contacts_tenant_id" in contact_indexes
    assert "ix_contacts_account_id" in contact_indexes
    assert "ix_source_evidence_tenant_id" in evidence_indexes
    assert "ix_source_evidence_workflow_run_id" in evidence_indexes
    assert "ix_source_evidence_account_id" in evidence_indexes
    assert "ix_source_evidence_contact_id" in evidence_indexes
    assert "ix_artifacts_tenant_id" in artifact_indexes
    assert "ix_artifacts_workflow_run_id" in artifact_indexes
    assert "ix_approval_decisions_tenant_id" in approval_indexes
    assert "ix_approval_decisions_workflow_run_id" in approval_indexes
    assert "ix_approval_decisions_artifact_id" in approval_indexes

    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
def test_migration_downgrade_returns_to_base_state() -> None:
    _async_url, sync_url = get_postgres_test_urls()
    _reset_database(sync_url)

    config = _alembic_config(sync_url)
    command.upgrade(config, "head")
    command.downgrade(config, "base")

    engine = create_engine(sync_url)
    inspector = inspect(engine)
    assert inspector.get_table_names() == ["alembic_version"]
    engine.dispose()


@pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"), reason="requires TEST_DATABASE_URL")
def test_migration_constraints_reject_invalid_and_duplicate_rows() -> None:
    _async_url, sync_url = get_postgres_test_urls()
    _reset_database(sync_url)

    config = _alembic_config(sync_url)
    command.upgrade(config, "head")

    engine = create_engine(sync_url)
    user_id = uuid4()
    tenant_id = uuid4()
    seller_id = uuid4()
    thread_id = uuid4()
    run_id = uuid4()
    account_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, external_auth_subject, status) "
                "VALUES (:user_id, 'subject-1', 'active')"
            ),
            {"user_id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO tenants (id, name, slug, status) "
                "VALUES (:tenant_id, 'Tenant One', 'tenant-one', 'active')"
            ),
            {"tenant_id": tenant_id},
        )
        connection.execute(
            text(
                "INSERT INTO seller_profiles "
                "(id, tenant_id, created_by_user_id, name, company_name, product_summary, value_proposition, source_status) "
                "VALUES (:seller_id, :tenant_id, :user_id, 'Seller', 'Acme', 'Summary', 'Value', 'manual')"
            ),
            {"seller_id": seller_id, "tenant_id": tenant_id, "user_id": user_id},
        )
        connection.execute(
            text(
                "INSERT INTO conversation_threads "
                "(id, tenant_id, created_by_user_id, seller_profile_id, status) "
                "VALUES (:thread_id, :tenant_id, :user_id, :seller_id, 'active')"
            ),
            {"thread_id": thread_id, "tenant_id": tenant_id, "user_id": user_id, "seller_id": seller_id},
        )
        connection.execute(
            text(
                "INSERT INTO workflow_runs "
                "(id, tenant_id, thread_id, created_by_user_id, workflow_type, status, requested_payload_json, correlation_id) "
                "VALUES (:run_id, :tenant_id, :thread_id, :user_id, 'account_search', 'queued', '{}'::jsonb, 'corr-1')"
            ),
            {"run_id": run_id, "tenant_id": tenant_id, "thread_id": thread_id, "user_id": user_id},
        )
        connection.execute(
            text(
                "UPDATE conversation_threads SET current_run_id = :run_id WHERE id = :thread_id"
            ),
            {"run_id": run_id, "thread_id": thread_id},
        )
        connection.execute(
            text(
                "INSERT INTO accounts "
                "(id, tenant_id, created_by_user_id, source_workflow_run_id, name, normalized_domain, status) "
                "VALUES (:account_id, :tenant_id, :user_id, :run_id, 'Account One', 'acme.example', 'accepted')"
            ),
            {"account_id": account_id, "tenant_id": tenant_id, "user_id": user_id, "run_id": run_id},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO workflow_runs "
                    "(id, tenant_id, created_by_user_id, workflow_type, status, requested_payload_json) "
                    "VALUES (:run_id, :tenant_id, :user_id, 'account_search', 'invalid', '{}'::jsonb)"
                ),
                {"run_id": uuid4(), "tenant_id": tenant_id, "user_id": user_id},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO workflow_runs "
                    "(id, tenant_id, created_by_user_id, workflow_type, status, requested_payload_json, correlation_id) "
                    "VALUES (:run_id, :tenant_id, :user_id, 'account_search', 'queued', '{}'::jsonb, 'corr-1')"
                ),
                {"run_id": uuid4(), "tenant_id": tenant_id, "user_id": user_id},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO run_events "
                    "(id, tenant_id, run_id, event_name, payload_json) "
                    "VALUES (:event_id, :tenant_id, :run_id, 'run.unknown', '{}'::jsonb)"
                ),
                {"event_id": uuid4(), "tenant_id": tenant_id, "run_id": run_id},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO accounts "
                    "(id, tenant_id, created_by_user_id, source_workflow_run_id, name, normalized_domain, status) "
                    "VALUES (:account_id, :tenant_id, :user_id, :run_id, 'Account Two', 'acme.example', 'accepted')"
                ),
                {"account_id": uuid4(), "tenant_id": tenant_id, "user_id": user_id, "run_id": run_id},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO artifacts "
                    "(id, tenant_id, workflow_run_id, artifact_type, format, title) "
                    "VALUES (:artifact_id, :tenant_id, :run_id, 'run_summary', 'markdown', 'Summary')"
                ),
                {"artifact_id": uuid4(), "tenant_id": tenant_id, "run_id": run_id},
            )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO approval_decisions "
                    "(id, tenant_id, workflow_run_id, reviewed_by_user_id, decision) "
                    "VALUES (:approval_id, :tenant_id, :run_id, :user_id, 'rejected')"
                ),
                {"approval_id": uuid4(), "tenant_id": tenant_id, "run_id": run_id, "user_id": user_id},
            )

    engine.dispose()
