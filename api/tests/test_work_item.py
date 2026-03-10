"""
Tests for Epic B2: WorkItem persistence.

Requires a live Postgres instance (DATABASE_URL env var).
Tests are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aose_api.models import WorkItem


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE: dict = dict(
    work_item_id="wi_b2_test_sample",
    entity_ref_type="account",
    entity_ref_id="account:SI-1234567",
    stage="account_discovery",
    payload_json={"v": 1, "data": {"query_object_id": "q_87f1"}},
    payload_version=1,
    attempt_budget_remaining=3,
    attempt_budget_policy="standard",
    idempotency_key="acctdisc:account:SI-1234567:q_87f1:v1",
    trace_run_id="run_abc123",
    trace_parent_work_item_id="wi_parent_001",
    trace_correlation_id="corr_account:SI-1234567",
    trace_policy_pack_id="safe_v0_1",
    created_at=datetime(2026, 2, 25, 10, 12, 33, tzinfo=timezone.utc),
)


@pytest.fixture(scope="session")
def db_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB tests")
    engine = create_engine(_sa_url(url))
    # Run migrations to ensure schema is current
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine):
    with Session(db_engine) as s:
        yield s


def _clean(session: Session, *work_item_ids: str) -> None:
    for wid in work_item_ids:
        row = session.get(WorkItem, wid)
        if row:
            session.delete(row)
    session.commit()


# ---------------------------------------------------------------------------
# Schema / model tests
# ---------------------------------------------------------------------------


def test_work_item_create_and_read(session):
    wid = "wi_b2_test_create_read"
    _clean(session, wid)

    wi = WorkItem(**{**SAMPLE, "work_item_id": wid})
    session.add(wi)
    session.commit()
    session.expire(wi)

    found = session.get(WorkItem, wid)
    assert found is not None
    assert found.work_item_id == wid
    assert found.entity_ref_type == "account"
    assert found.entity_ref_id == "account:SI-1234567"
    assert found.stage == "account_discovery"
    assert found.attempt_budget_remaining == 3
    assert found.attempt_budget_policy == "standard"
    assert found.idempotency_key == "acctdisc:account:SI-1234567:q_87f1:v1"
    assert found.trace_run_id == "run_abc123"
    assert found.trace_parent_work_item_id == "wi_parent_001"
    assert found.trace_correlation_id == "corr_account:SI-1234567"
    assert found.trace_policy_pack_id == "safe_v0_1"
    assert found.created_at is not None

    _clean(session, wid)


def test_null_parent_work_item_id(session):
    wid = "wi_b2_test_null_parent"
    _clean(session, wid)

    wi = WorkItem(**{**SAMPLE, "work_item_id": wid, "trace_parent_work_item_id": None})
    session.add(wi)
    session.commit()
    session.expire(wi)

    found = session.get(WorkItem, wid)
    assert found.trace_parent_work_item_id is None

    _clean(session, wid)


def test_payload_roundtrip(session):
    wid = "wi_b2_test_payload_rt"
    _clean(session, wid)

    payload = {"v": 2, "data": {"key": "value", "nested": {"x": 42}}}
    wi = WorkItem(
        **{**SAMPLE, "work_item_id": wid, "payload_json": payload, "payload_version": 2}
    )
    session.add(wi)
    session.commit()
    session.expire(wi)

    found = session.get(WorkItem, wid)
    assert found.payload_json == payload
    assert found.payload_version == 2

    _clean(session, wid)


def test_payload_version_stored_separately(session):
    """payload_version column is independent from payload_json body."""
    wid = "wi_b2_test_pv_sep"
    _clean(session, wid)

    wi = WorkItem(**{**SAMPLE, "work_item_id": wid, "payload_version": 7})
    session.add(wi)
    session.commit()
    session.expire(wi)

    found = session.get(WorkItem, wid)
    assert found.payload_version == 7

    _clean(session, wid)


# ---------------------------------------------------------------------------
# Migration / schema inspection tests
# ---------------------------------------------------------------------------


def test_work_items_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "work_items" in inspector.get_table_names()


def test_required_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    index_names = {idx["name"] for idx in inspector.get_indexes("work_items")}
    assert "ix_work_items_stage" in index_names
    assert "ix_work_items_idempotency_key" in index_names
    assert "ix_work_items_entity_ref" in index_names


def test_idempotency_key_unique_constraint_exists(db_engine):
    inspector = inspect(db_engine)
    uq_names = {u["name"] for u in inspector.get_unique_constraints("work_items")}
    assert "uq_work_items_idempotency_key" in uq_names


def test_replay_same_idempotency_key_rejected(session):
    """DB must reject two WorkItems with the same idempotency_key."""
    wid1 = "wi_b2_test_idem_replay_1"
    wid2 = "wi_b2_test_idem_replay_2"
    _clean(session, wid1, wid2)

    wi1 = WorkItem(**{**SAMPLE, "work_item_id": wid1})
    session.add(wi1)
    session.commit()

    with Session(session.bind) as s2:
        wi2 = WorkItem(**{**SAMPLE, "work_item_id": wid2})
        s2.add(wi2)
        with pytest.raises(IntegrityError):
            s2.commit()

    _clean(session, wid1, wid2)


# ---------------------------------------------------------------------------
# Contract guard tests
# ---------------------------------------------------------------------------


def test_no_separate_trace_table(db_engine):
    """Trace must be embedded on work_items — no separate table."""
    inspector = inspect(db_engine)
    tables = inspector.get_table_names()
    assert "trace" not in tables
    assert "traces" not in tables


def test_work_items_coexist_with_all_epic_c_tables(db_engine):
    # structured_events was added in Epic C — work_items must still coexist
    tables = inspect(db_engine).get_table_names()
    assert "work_items" in tables
    assert "structured_events" in tables


# ---------------------------------------------------------------------------
# API verification surface tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def api_client(db_engine):
    from aose_api.main import app

    with TestClient(app) as client:
        yield client


def test_api_create_and_fetch_work_item(api_client, session):
    wid = "wi_b2_test_api_create"
    _clean(session, wid)

    payload = {
        **SAMPLE,
        "work_item_id": wid,
        "created_at": "2026-02-25T10:12:33+00:00",
    }
    r = api_client.post("/work-items", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["work_item_id"] == wid
    assert body["stage"] == "account_discovery"
    assert body["payload_json"] == SAMPLE["payload_json"]

    r2 = api_client.get(f"/work-items/{wid}")
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["work_item_id"] == wid
    assert body2["entity_ref_type"] == "account"
    assert body2["entity_ref_id"] == "account:SI-1234567"
    assert body2["trace_policy_pack_id"] == "safe_v0_1"
    assert body2["payload_json"] == SAMPLE["payload_json"]

    _clean(session, wid)


def test_api_get_nonexistent_returns_404(api_client):
    r = api_client.get("/work-items/wi_does_not_exist_xyz")
    assert r.status_code == 404
