"""
Tests for SPEC-H3: Approval workflow handler.

Acceptance checks covered:
  unit: decision_key is deterministic for same inputs
  unit: decision_key differs for different inputs
  unit: decision_id follows locked formula decision:<draft_id>:<key>
  unit: dispatch_idempotency_key follows locked formula
  unit: check_authority allows operator
  unit: check_authority allows admin
  unit: check_authority raises AuthorityError for viewer
  unit: check_status accepts all locked statuses
  unit: check_status raises InvalidStatusError for unlocked value
  unit: get_next_stage maps approved → sending_dispatch
  unit: get_next_stage maps rejected → parked:rejected
  unit: get_next_stage maps needs_rewrite → parked:needs_rewrite
  unit: get_next_stage maps needs_more_evidence → parked:needs_more_evidence
  integration: handler parks needs_human when no decision data in payload
  integration: handler persists ApprovalDecision and enqueues sending_dispatch on approved
  integration: handler persists ApprovalDecision and enqueues parked:rejected on rejected
  integration: handler replay reuses existing decision_id via decision_key
  integration: handler parks contract_error when viewer attempts approval
  integration: handler parks contract_error when status is invalid
  integration: handler parks contract_error when draft_id missing
  integration: handler parks contract_error when draft not found
  integration: approval_recorded event emitted on success
  integration: work_item_completed terminal event on approved
  integration: work_item_parked terminal event on rejected

Integration tests require a live Postgres instance (DATABASE_URL env var).
They are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import (
    make_decision_id,
    make_decision_key,
    make_dispatch_idempotency_key,
    make_draft_id,
)
from aose_worker.services.approval_decision_service import (
    ACTION_TYPE_DEFAULT,
    AuthorityError,
    InvalidStatusError,
    check_authority,
    check_status,
    get_next_stage,
)


# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------


ACCOUNT_ID = "account:SI-7700001"
CONTACT_ID = f"contact:{ACCOUNT_ID}:dana.test@example.si"
WORK_ITEM_ID = "wi_h3_unit_test"
DRAFT_ID = make_draft_id(contact_id=CONTACT_ID, sequence_no=1, variant_no=1)
POLICY_PACK_ID = "safe_v0_1"
ACTION_TYPE = ACTION_TYPE_DEFAULT

_BASE_KEY_KWARGS = dict(
    work_item_id=WORK_ITEM_ID,
    contact_id=CONTACT_ID,
    action_type=ACTION_TYPE,
    policy_pack_id=POLICY_PACK_ID,
    draft_id=DRAFT_ID,
)


def test_decision_key_deterministic():
    k1 = make_decision_key(**_BASE_KEY_KWARGS)
    k2 = make_decision_key(**_BASE_KEY_KWARGS)
    assert k1 == k2


def test_decision_key_differs_on_different_work_item():
    k1 = make_decision_key(**_BASE_KEY_KWARGS)
    k2 = make_decision_key(**{**_BASE_KEY_KWARGS, "work_item_id": "wi_other"})
    assert k1 != k2


def test_decision_key_differs_on_different_draft():
    k1 = make_decision_key(**_BASE_KEY_KWARGS)
    k2 = make_decision_key(**{**_BASE_KEY_KWARGS, "draft_id": "draft:other"})
    assert k1 != k2


def test_decision_id_follows_locked_formula():
    dk = make_decision_key(**_BASE_KEY_KWARGS)
    did = make_decision_id(draft_id=DRAFT_ID, decision_key=dk)
    assert did == f"decision:{DRAFT_ID}:{dk}"


def test_dispatch_idempotency_key_formula():
    dk = make_decision_key(**_BASE_KEY_KWARGS)
    did = make_decision_id(draft_id=DRAFT_ID, decision_key=dk)
    ik = make_dispatch_idempotency_key(draft_id=DRAFT_ID, decision_id=did)
    assert ik == f"dispatch:{DRAFT_ID}:{did}:v1"


def test_check_authority_allows_operator():
    check_authority("operator")  # must not raise


def test_check_authority_allows_admin():
    check_authority("admin")  # must not raise


def test_check_authority_rejects_viewer():
    with pytest.raises(AuthorityError):
        check_authority("viewer")


def test_check_authority_rejects_unknown_role():
    with pytest.raises(AuthorityError):
        check_authority("superuser")


def test_check_status_accepts_all_locked_statuses():
    for s in ("approved", "rejected", "needs_rewrite", "needs_more_evidence"):
        check_status(s)  # must not raise


def test_check_status_rejects_unlocked():
    with pytest.raises(InvalidStatusError):
        check_status("pending")


def test_check_status_rejects_invented():
    with pytest.raises(InvalidStatusError):
        check_status("escalated")


def test_get_next_stage_approved():
    assert get_next_stage("approved") == "sending_dispatch"


def test_get_next_stage_rejected():
    assert get_next_stage("rejected") == "parked:rejected"


def test_get_next_stage_needs_rewrite():
    assert get_next_stage("needs_rewrite") == "parked:needs_rewrite"


def test_get_next_stage_needs_more_evidence():
    assert get_next_stage("needs_more_evidence") == "parked:needs_more_evidence"


# ---------------------------------------------------------------------------
# Integration test helpers and fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
_DB_ACCOUNT_ID = "account:SI-7700002"
# Use LinkedIn-hash contact ID so the canonical ID contains no email address
# (draft_id embeds contact_id; a raw email would trip the structured-event PII check)
_LI_HASH = hashlib.sha256(b"https://linkedin.com/in/dana-h3").hexdigest()
_DB_CONTACT_ID = f"contact:{_DB_ACCOUNT_ID}:{_LI_HASH}"
_DB_DRAFT_ID = make_draft_id(contact_id=_DB_CONTACT_ID, sequence_no=1, variant_no=1)
_DB_POLICY_PACK_ID = "safe_v0_1"


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture(scope="session")
def db_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB tests")
    # Schema migrations are managed by the API container (alembic).
    # The worker assumes the schema is already current when DATABASE_URL is set.
    engine = create_engine(_sa_url(url))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def seed_fixtures(db_engine):
    """Ensure account, contact, and draft rows exist for H3 handler tests."""
    with Session(db_engine) as s:
        s.execute(
            text(
                """
                INSERT INTO accounts (account_id, name, domain, country, provenance,
                                      evidence_ids, confidence, status, v)
                VALUES (:aid, 'Test H3 Corp', NULL, 'SI', '[]'::jsonb,
                        '[]'::jsonb, 0.9, 'candidate', 1)
                ON CONFLICT (account_id) DO NOTHING
                """
            ),
            {"aid": _DB_ACCOUNT_ID},
        )
        s.execute(
            text(
                """
                INSERT INTO contacts (contact_id, account_id, full_name,
                                      channels_json, provenance_json, status, v)
                VALUES (:cid, :aid, 'Dana H3', '[]', '[]', 'candidate', 1)
                ON CONFLICT (contact_id) DO NOTHING
                """
            ),
            {"cid": _DB_CONTACT_ID, "aid": _DB_ACCOUNT_ID},
        )
        s.execute(
            text(
                """
                INSERT INTO outreach_drafts (draft_id, contact_id, account_id, channel,
                                            language, policy_pack_id, subject, body, risk_flags_json,
                                            created_at, v)
                VALUES (:did, :cid, :aid, 'email', 'en', 'safe_v0_1', 'Test subject', 'Test body',
                        '[]'::jsonb, :ts, 1)
                ON CONFLICT (draft_id) DO NOTHING
                """
            ),
            {
                "did": _DB_DRAFT_ID,
                "cid": _DB_CONTACT_ID,
                "aid": _DB_ACCOUNT_ID,
                "ts": _NOW,
            },
        )
        s.commit()
    yield


def _make_work_item(
    *,
    db_engine,
    work_item_id: str,
    payload_data: dict,
    stage: str = "approval_request",
) -> None:
    """Insert a work_item row for handler testing."""
    payload_json = {"v": 1, "data": payload_data}
    idempotency_key = f"h3test:{work_item_id}"
    with Session(db_engine) as s:
        s.execute(
            text(
                """
                INSERT INTO work_items (
                    work_item_id, entity_ref_type, entity_ref_id, stage,
                    payload_json, payload_version,
                    attempt_budget_remaining, attempt_budget_policy,
                    idempotency_key,
                    trace_run_id, trace_parent_work_item_id,
                    trace_correlation_id, trace_policy_pack_id, created_at
                ) VALUES (
                    :wi_id, 'contact', :eid, :stage,
                    CAST(:payload AS JSONB), 1,
                    3, 'standard',
                    :ik,
                    'run_h3_test', NULL, :corr, :ppid, now()
                ) ON CONFLICT (idempotency_key) DO NOTHING
                """
            ),
            {
                "wi_id": work_item_id,
                "eid": _DB_CONTACT_ID,
                "stage": stage,
                "payload": json.dumps(payload_json),
                "ik": idempotency_key,
                "corr": f"corr:{_DB_ACCOUNT_ID}",
                "ppid": _DB_POLICY_PACK_ID,
            },
        )
        s.commit()


def _clean_decision_by_key(db_engine, decision_key: str) -> None:
    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM approval_decisions WHERE decision_key = :dk"),
            {"dk": decision_key},
        )
        s.commit()


def _clean_work_item(db_engine, work_item_id: str) -> None:
    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM structured_events WHERE work_item_id = :wi"),
            {"wi": work_item_id},
        )
        # approval_decisions has FK to work_items — delete it first
        s.execute(
            text("DELETE FROM approval_decisions WHERE work_item_id = :wi"),
            {"wi": work_item_id},
        )
        s.execute(
            text("DELETE FROM work_items WHERE work_item_id = :wi"),
            {"wi": work_item_id},
        )
        s.commit()


def _get_decision_count(db_engine, draft_id: str, decision_key: str) -> int:
    with Session(db_engine) as s:
        row = s.execute(
            text(
                "SELECT COUNT(*) FROM approval_decisions "
                "WHERE draft_id = :did AND decision_key = :dk"
            ),
            {"did": draft_id, "dk": decision_key},
        ).first()
        return int(row[0]) if row else 0


def _get_next_stage_work_item(db_engine, idempotency_key: str) -> dict | None:
    with Session(db_engine) as s:
        row = (
            s.execute(
                text(
                    "SELECT stage, payload_json FROM work_items WHERE idempotency_key = :ik"
                ),
                {"ik": idempotency_key},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None


def _get_events(db_engine, work_item_id: str) -> list[dict]:
    with Session(db_engine) as s:
        rows = (
            s.execute(
                text(
                    "SELECT event_type, outcome, error_code "
                    "FROM structured_events WHERE work_item_id = :wi "
                    "ORDER BY occurred_at"
                ),
                {"wi": work_item_id},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_handler_parks_needs_human_on_missing_decision_data(db_engine, seed_fixtures):
    """Initial copy_generate enqueue (draft_id only) should park as needs_human."""
    wi_id = "wi_h3_needs_human_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID},
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    handle_approval_request({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    event_types = [e["event_type"] for e in events]
    assert "handler_started" in event_types
    assert "work_item_parked" in event_types
    parked = next(e for e in events if e["event_type"] == "work_item_parked")
    assert parked["error_code"] == "needs_human"

    _clean_work_item(db_engine, wi_id)


def test_handler_approved_persists_decision_and_enqueues_sending_dispatch(
    db_engine, seed_fixtures
):
    """approved status → ApprovalDecision stored, sending_dispatch enqueued."""
    wi_id = "wi_h3_approved_01"
    _clean_work_item(db_engine, wi_id)
    dk = make_decision_key(
        work_item_id=wi_id,
        contact_id=_DB_CONTACT_ID,
        action_type=ACTION_TYPE_DEFAULT,
        policy_pack_id=_DB_POLICY_PACK_ID,
        draft_id=_DB_DRAFT_ID,
    )
    _clean_decision_by_key(db_engine, dk)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={
            "draft_id": _DB_DRAFT_ID,
            "status": "approved",
            "reviewer_id": "reviewer:op-001",
            "reviewer_role": "operator",
        },
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    handle_approval_request({"work_item_id": wi_id})

    # ApprovalDecision stored
    count = _get_decision_count(db_engine, _DB_DRAFT_ID, dk)
    assert count == 1

    # sending_dispatch WorkItem enqueued
    did = make_decision_id(draft_id=_DB_DRAFT_ID, decision_key=dk)
    ik = make_dispatch_idempotency_key(draft_id=_DB_DRAFT_ID, decision_id=did)
    next_wi = _get_next_stage_work_item(db_engine, ik)
    assert next_wi is not None
    assert next_wi["stage"] == "sending_dispatch"
    payload = next_wi["payload_json"]
    assert payload["data"]["draft_id"] == _DB_DRAFT_ID
    assert payload["data"]["decision_id"] == did

    # Structured events: approval_recorded + work_item_completed
    events = _get_events(db_engine, wi_id)
    event_types = [e["event_type"] for e in events]
    assert "approval_recorded" in event_types
    assert "work_item_completed" in event_types

    _clean_decision_by_key(db_engine, dk)
    _clean_work_item(db_engine, wi_id)


def test_handler_rejected_persists_decision_and_enqueues_parked_rejected(
    db_engine, seed_fixtures
):
    """rejected status → parked:rejected WorkItem enqueued."""
    wi_id = "wi_h3_rejected_01"
    _clean_work_item(db_engine, wi_id)
    dk = make_decision_key(
        work_item_id=wi_id,
        contact_id=_DB_CONTACT_ID,
        action_type=ACTION_TYPE_DEFAULT,
        policy_pack_id=_DB_POLICY_PACK_ID,
        draft_id=_DB_DRAFT_ID,
    )
    _clean_decision_by_key(db_engine, dk)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={
            "draft_id": _DB_DRAFT_ID,
            "status": "rejected",
            "reviewer_id": "reviewer:op-001",
            "reviewer_role": "operator",
        },
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    handle_approval_request({"work_item_id": wi_id})

    did = make_decision_id(
        draft_id=_DB_DRAFT_ID,
        decision_key=dk,
    )
    ik = make_dispatch_idempotency_key(draft_id=_DB_DRAFT_ID, decision_id=did)
    next_wi = _get_next_stage_work_item(db_engine, ik)
    assert next_wi is not None
    assert next_wi["stage"] == "parked:rejected"

    events = _get_events(db_engine, wi_id)
    event_types = [e["event_type"] for e in events]
    assert "approval_recorded" in event_types
    assert "work_item_parked" in event_types

    _clean_decision_by_key(db_engine, dk)
    _clean_work_item(db_engine, wi_id)


def test_handler_replay_reuses_decision_id(db_engine, seed_fixtures):
    """
    Replay safety: running the handler twice for the same work_item produces
    exactly one ApprovalDecision and reuses the same decision_id.
    """
    wi_id = "wi_h3_replay_01"
    _clean_work_item(db_engine, wi_id)
    dk = make_decision_key(
        work_item_id=wi_id,
        contact_id=_DB_CONTACT_ID,
        action_type=ACTION_TYPE_DEFAULT,
        policy_pack_id=_DB_POLICY_PACK_ID,
        draft_id=_DB_DRAFT_ID,
    )
    _clean_decision_by_key(db_engine, dk)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={
            "draft_id": _DB_DRAFT_ID,
            "status": "approved",
            "reviewer_id": "reviewer:op-001",
            "reviewer_role": "operator",
        },
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    # Run once
    handle_approval_request({"work_item_id": wi_id})
    count_after_first = _get_decision_count(db_engine, _DB_DRAFT_ID, dk)
    assert count_after_first == 1

    # Run again (same work_item_id → same decision_key → ON CONFLICT DO NOTHING)
    handle_approval_request({"work_item_id": wi_id})
    count_after_second = _get_decision_count(db_engine, _DB_DRAFT_ID, dk)
    assert count_after_second == 1  # still exactly one

    _clean_decision_by_key(db_engine, dk)
    _clean_work_item(db_engine, wi_id)


def test_handler_viewer_parks_contract_error(db_engine, seed_fixtures):
    """Viewer attempting approval must park with contract_error."""
    wi_id = "wi_h3_viewer_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={
            "draft_id": _DB_DRAFT_ID,
            "status": "approved",
            "reviewer_id": "reviewer:viewer-001",
            "reviewer_role": "viewer",
        },
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    handle_approval_request({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_invalid_status_parks_contract_error(db_engine, seed_fixtures):
    """Invalid status value must park with contract_error."""
    wi_id = "wi_h3_badstatus_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={
            "draft_id": _DB_DRAFT_ID,
            "status": "pending",
            "reviewer_id": "reviewer:op-001",
            "reviewer_role": "operator",
        },
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    handle_approval_request({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_missing_draft_id_parks_contract_error(db_engine, seed_fixtures):
    """Missing draft_id in payload must park with contract_error."""
    wi_id = "wi_h3_nodraft_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={},
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    handle_approval_request({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_draft_not_found_parks_contract_error(db_engine, seed_fixtures):
    """Non-existent draft_id must park with contract_error."""
    wi_id = "wi_h3_baddraft_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": "draft:nonexistent:seq99:v99"},
    )

    from aose_worker.handlers.approval_request import handle_approval_request

    handle_approval_request({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)
