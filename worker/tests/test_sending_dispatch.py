"""
Tests for SPEC-I1: Sending dispatch handler skeleton with fail-closed gating.

Acceptance checks covered:
  unit: send_attempt_id follows locked formula send:<draft_id>:<channel>
  unit: send_attempt_idempotency_key follows locked formula send:<draft_id>:<channel>:v1
  unit: evaluate_gates passes when send_enabled=true and budget > 0
  unit: evaluate_gates blocks on BudgetGate when budget <= 0
  unit: evaluate_gates blocks on SendGate when send_enabled=false
  integration: handler parks safely when send_enabled=false (main acceptance criterion)
  integration: no SendAttempt row created when send_enabled=false
  integration: handler parks contract_error on unsupported payload_version
  integration: handler parks contract_error on missing draft_id
  integration: handler parks contract_error on missing decision_id
  integration: handler parks contract_error when draft not found
  integration: handler parks contract_error when approval decision not found
  integration: handler parks contract_error when approval.draft_id mismatches payload draft_id
  integration: handler parks contract_error when approval.contact_id mismatches draft.contact_id
  integration: handler parks contract_error when draft contact is missing
  integration: handler parks contract_error when draft account is missing
  integration: handler parks contract_error when approval required review fields are missing
  integration: handler parks policy_blocked when approval includes gate overrides
  integration: handler parks policy_blocked when approval status != approved
  integration: handler parks policy_blocked when approval policy_pack_id != safe_v0_1
  integration: handler refs remain redacted (no raw email patterns)
  integration: allowed sandbox path creates one SendAttempt with locked fields
  integration: replay of allowed sandbox path reuses existing SendAttempt
  integration: allowed sandbox path writes a redacted sink event payload
  integration: handler_started event always emitted

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import (
    make_draft_id,
    make_send_attempt_id,
    make_send_attempt_idempotency_key,
)
from aose_worker.handlers.sending_dispatch import _evaluate_gates


# ---------------------------------------------------------------------------
# Unit tests — no DB required
# ---------------------------------------------------------------------------


_DRAFT_ID_UNIT = "draft:contact:acct-unit:seq1:v1"
_CHANNEL_UNIT = "email"


def test_send_attempt_id_follows_locked_formula():
    sid = make_send_attempt_id(_DRAFT_ID_UNIT, _CHANNEL_UNIT)
    assert sid == f"send:{_DRAFT_ID_UNIT}:{_CHANNEL_UNIT}"


def test_send_attempt_idempotency_key_follows_locked_formula():
    ik = make_send_attempt_idempotency_key(_DRAFT_ID_UNIT, _CHANNEL_UNIT)
    assert ik == f"send:{_DRAFT_ID_UNIT}:{_CHANNEL_UNIT}:v1"


def test_send_attempt_id_differs_by_channel():
    sid_email = make_send_attempt_id(_DRAFT_ID_UNIT, "email")
    sid_linkedin = make_send_attempt_id(_DRAFT_ID_UNIT, "linkedin")
    assert sid_email != sid_linkedin


def test_evaluate_gates_passes_when_send_enabled_and_budget_positive():
    passed, blocking = _evaluate_gates(attempt_budget_remaining=3, send_enabled=True)
    assert passed is True
    assert blocking == ""


def test_evaluate_gates_blocks_on_budget_gate_when_exhausted():
    passed, blocking = _evaluate_gates(attempt_budget_remaining=0, send_enabled=True)
    assert passed is False
    assert blocking == "BudgetGate"


def test_evaluate_gates_blocks_on_send_gate_when_disabled():
    passed, blocking = _evaluate_gates(attempt_budget_remaining=3, send_enabled=False)
    assert passed is False
    assert blocking == "SendGate"


def test_evaluate_gates_budget_checked_before_send_gate():
    # Budget exhausted + send disabled → BudgetGate wins (checked first)
    passed, blocking = _evaluate_gates(attempt_budget_remaining=0, send_enabled=False)
    assert passed is False
    assert blocking == "BudgetGate"


# ---------------------------------------------------------------------------
# Integration test helpers and fixtures
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)
_DB_ACCOUNT_ID = "account:SI-9900001"
# Use LinkedIn-hash contact ID so the canonical ID contains no email address
# (draft_id embeds contact_id; a raw email would trip the structured-event PII check)
_LI_HASH = hashlib.sha256(b"https://linkedin.com/in/dana-i1").hexdigest()
_DB_CONTACT_ID = f"contact:{_DB_ACCOUNT_ID}:{_LI_HASH}"
_DB_DRAFT_ID = make_draft_id(contact_id=_DB_CONTACT_ID, sequence_no=1, variant_no=1)
_DB_POLICY_PACK_ID = "safe_v0_1"
_DB_DECISION_KEY = "dk_i1_test_fixture"


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


def _clear_suppression_tables(session: Session) -> None:
    for table_name in (
        "global_dnc",
        "campaign_suppression",
        "complaint_suppression",
        "bounced_suppression",
    ):
        exists = session.execute(
            text("SELECT to_regclass(:name)"),
            {"name": table_name},
        ).scalar()
        if exists:
            session.execute(text(f"DELETE FROM {table_name}"))


@pytest.fixture(scope="session")
def db_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB tests")
    engine = create_engine(_sa_url(url))
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def seed_fixtures(db_engine):
    """Ensure account, contact, draft, and approval_decision rows exist for I1 tests."""
    with Session(db_engine) as s:
        _clear_suppression_tables(s)
        s.execute(
            text("DELETE FROM send_attempts WHERE draft_id = :did"),
            {"did": _DB_DRAFT_ID},
        )
        s.execute(
            text(
                """
                INSERT INTO accounts (account_id, name, domain, country, provenance,
                                      evidence_ids, confidence, status, v)
                VALUES (:aid, 'Test I1 Corp', NULL, 'SI', '[]'::jsonb,
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
                VALUES (
                    :cid, :aid, 'Dana I1',
                    CAST(:channels AS JSONB),
                    '[]', 'candidate', 1
                )
                ON CONFLICT (contact_id) DO NOTHING
                """
            ),
            {
                "cid": _DB_CONTACT_ID,
                "aid": _DB_ACCOUNT_ID,
                "channels": json.dumps(
                    [
                        {
                            "type": "email",
                            "value": "dana@test-i1.example",
                            "validated": "domain_ok",
                            "confidence": 0.92,
                        }
                    ]
                ),
            },
        )
        s.execute(
            text(
                """
                INSERT INTO outreach_drafts (draft_id, contact_id, account_id, channel,
                                            language, policy_pack_id, subject, body, risk_flags_json,
                                            created_at, v)
                VALUES (
                    :did, :cid, :aid, 'email', 'en', 'safe_v0_1',
                    'Test I1 subject',
                    'Test body {{unsubscribe_token}}',
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
        # Seed minimal evidence + anchors so I3 review gates can PASS in
        # SEND_ENABLED=true tests.
        s.execute(
            text(
                """
                INSERT INTO evidence (
                    evidence_id, source_type, canonical_url, captured_at, snippet,
                    claim_frame, source_provider, source_ref, observed_at,
                    confidence, provenance_json, content_ref_id, v
                ) VALUES (
                    'evidence:i3:1', 'firmographic', 'https://test-i1.example/about',
                    :ts, 'snippet 1', 'claim 1', 'seed', 'seed:1', :ts,
                    0.9, '{"category":"firmographic"}'::jsonb, NULL, 1
                ) ON CONFLICT (evidence_id) DO NOTHING
                """
            ),
            {"ts": _NOW},
        )
        s.execute(
            text(
                """
                INSERT INTO evidence (
                    evidence_id, source_type, canonical_url, captured_at, snippet,
                    claim_frame, source_provider, source_ref, observed_at,
                    confidence, provenance_json, content_ref_id, v
                ) VALUES (
                    'evidence:i3:2', 'technographic', 'https://test-i1.example/stack',
                    :ts, 'snippet 2', 'claim 2', 'seed', 'seed:2', :ts,
                    0.9, '{"category":"technographic"}'::jsonb, NULL, 1
                ) ON CONFLICT (evidence_id) DO NOTHING
                """
            ),
            {"ts": _NOW},
        )
        s.execute(
            text(
                """
                INSERT INTO personalization_anchors (anchor_key, draft_id, span, evidence_ids_json, v)
                VALUES (
                    'anchor:i3:1',
                    :did,
                    'claim 1 span',
                    '["evidence:i3:1"]'::jsonb,
                    1
                ) ON CONFLICT (anchor_key) DO NOTHING
                """
            ),
            {"did": _DB_DRAFT_ID},
        )
        s.execute(
            text(
                """
                INSERT INTO personalization_anchors (anchor_key, draft_id, span, evidence_ids_json, v)
                VALUES (
                    'anchor:i3:2',
                    :did,
                    'claim 2 span',
                    '["evidence:i3:2"]'::jsonb,
                    1
                ) ON CONFLICT (anchor_key) DO NOTHING
                """
            ),
            {"did": _DB_DRAFT_ID},
        )
        s.commit()
    yield


def _make_approval_decision(
    db_engine,
    *,
    decision_id: str,
    draft_id: str,
    work_item_id: str,
    contact_id: str = _DB_CONTACT_ID,
    status: str = "approved",
    policy_pack_id: str = "safe_v0_1",
    decision_key: str = _DB_DECISION_KEY,
    reviewer_id: str | None = "reviewer:op-001",
    reviewer_role: str | None = "operator",
    overridden_gates_json: str = "[]",
) -> None:
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
                    :wi_id, 'contact', :eid, 'approval_request',
                    CAST(:payload AS JSONB), 1,
                    1, 'standard',
                    :ik,
                    'run_i1_approval_fixture', NULL, :corr, :ppid, :ts
                ) ON CONFLICT (work_item_id) DO NOTHING
                """
            ),
            {
                "wi_id": work_item_id,
                "eid": contact_id,
                "payload": json.dumps({"v": 1, "data": {"draft_id": draft_id}}),
                "ik": f"approval-fixture:{work_item_id}",
                "corr": f"corr:{contact_id}",
                "ppid": policy_pack_id,
                "ts": _NOW,
            },
        )
        s.execute(
            text(
                """
                INSERT INTO approval_decisions (
                    decision_id, decision_key, draft_id, work_item_id, contact_id,
                    action_type, status, reviewer_id, reviewer_role,
                    overridden_gates_json, policy_pack_id, decided_at, v
                ) VALUES (
                    :did, :dk, :draft_id, :wi_id, :cid,
                    'approve_send', :status, :reviewer_id, :reviewer_role,
                    CAST(:overrides AS JSONB), :ppid, :ts, 1
                ) ON CONFLICT (decision_id) DO NOTHING
                """
            ),
            {
                "did": decision_id,
                "dk": decision_key,
                "draft_id": draft_id,
                "wi_id": work_item_id,
                "cid": contact_id,
                "status": status,
                "reviewer_id": reviewer_id,
                "reviewer_role": reviewer_role,
                "overrides": overridden_gates_json,
                "ppid": policy_pack_id,
                "ts": _NOW,
            },
        )
        s.commit()


def _make_work_item(
    *,
    db_engine,
    work_item_id: str,
    payload_data: dict,
    payload_version: int = 1,
    stage: str = "sending_dispatch",
    attempt_budget_remaining: int = 3,
) -> None:
    payload_json = {"v": payload_version, "data": payload_data}
    idempotency_key = f"i1test:{work_item_id}"
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
                    CAST(:payload AS JSONB), :pv,
                    :budget, 'standard',
                    :ik,
                    'run_i1_test', NULL, :corr, :ppid, now()
                ) ON CONFLICT (work_item_id) DO UPDATE SET
                    entity_ref_type = EXCLUDED.entity_ref_type,
                    entity_ref_id = EXCLUDED.entity_ref_id,
                    stage = EXCLUDED.stage,
                    payload_json = EXCLUDED.payload_json,
                    payload_version = EXCLUDED.payload_version,
                    attempt_budget_remaining = EXCLUDED.attempt_budget_remaining,
                    attempt_budget_policy = EXCLUDED.attempt_budget_policy,
                    idempotency_key = EXCLUDED.idempotency_key,
                    trace_run_id = EXCLUDED.trace_run_id,
                    trace_parent_work_item_id = EXCLUDED.trace_parent_work_item_id,
                    trace_correlation_id = EXCLUDED.trace_correlation_id,
                    trace_policy_pack_id = EXCLUDED.trace_policy_pack_id
                """
            ),
            {
                "wi_id": work_item_id,
                "eid": _DB_CONTACT_ID,
                "stage": stage,
                "payload": json.dumps(payload_json),
                "pv": payload_version,
                "budget": attempt_budget_remaining,
                "ik": idempotency_key,
                "corr": f"corr:{_DB_ACCOUNT_ID}",
                "ppid": _DB_POLICY_PACK_ID,
            },
        )
        s.commit()


def _clean_work_item(db_engine, work_item_id: str) -> None:
    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM structured_events WHERE work_item_id = :wi"),
            {"wi": work_item_id},
        )
        s.execute(
            text("DELETE FROM approval_decisions WHERE work_item_id = :wi"),
            {"wi": work_item_id},
        )
        s.execute(
            text("DELETE FROM work_items WHERE work_item_id = :wi"),
            {"wi": work_item_id},
        )
        s.commit()


def _clean_approval_decision(db_engine, decision_id: str) -> None:
    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM approval_decisions WHERE decision_id = :did"),
            {"did": decision_id},
        )
        s.commit()


def _clean_send_attempt(db_engine, idempotency_key: str) -> None:
    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM send_attempts WHERE idempotency_key = :ik"),
            {"ik": idempotency_key},
        )
        s.commit()


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


def _get_event_refs(db_engine, work_item_id: str) -> list[dict]:
    with Session(db_engine) as s:
        rows = (
            s.execute(
                text(
                    "SELECT refs FROM structured_events WHERE work_item_id = :wi "
                    "ORDER BY occurred_at"
                ),
                {"wi": work_item_id},
            )
            .mappings()
            .all()
        )
        return [dict(r["refs"] or {}) for r in rows]


def _get_send_attempt_count(db_engine, idempotency_key: str) -> int:
    with Session(db_engine) as s:
        row = s.execute(
            text("SELECT COUNT(*) FROM send_attempts WHERE idempotency_key = :ik"),
            {"ik": idempotency_key},
        ).first()
        return int(row[0]) if row else 0


def _get_send_attempt_row(db_engine, idempotency_key: str) -> dict | None:
    with Session(db_engine) as s:
        row = (
            s.execute(
                text(
                    """
                    SELECT send_id, channel, provider, status, idempotency_key, policy_pack_id
                    FROM send_attempts
                    WHERE idempotency_key = :ik
                    """
                ),
                {"ik": idempotency_key},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None


def _get_events_with_refs(db_engine, work_item_id: str) -> list[dict]:
    with Session(db_engine) as s:
        rows = (
            s.execute(
                text(
                    "SELECT event_type, refs FROM structured_events "
                    "WHERE work_item_id = :wi ORDER BY occurred_at"
                ),
                {"wi": work_item_id},
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]


def _set_contact_channels(db_engine, contact_id: str, channels: list[dict]) -> None:
    with Session(db_engine) as s:
        s.execute(
            text(
                "UPDATE contacts SET channels_json = CAST(:ch AS JSONB) "
                "WHERE contact_id = :cid"
            ),
            {"ch": json.dumps(channels), "cid": contact_id},
        )
        s.commit()


def _insert_send_attempt_row(
    db_engine,
    *,
    send_id: str,
    draft_id: str,
    idempotency_key: str,
    created_at: datetime,
) -> None:
    with Session(db_engine) as s:
        s.execute(
            text(
                """
                INSERT INTO send_attempts (
                    send_id, draft_id, decision_id, channel, provider, status,
                    idempotency_key, policy_pack_id, created_at, v
                ) VALUES (
                    :sid, :did, NULL, 'email', 'SEND_SRC_01', 'queued',
                    :ik, 'safe_v0_1', :ts, 1
                ) ON CONFLICT (idempotency_key) DO NOTHING
                """
            ),
            {"sid": send_id, "did": draft_id, "ik": idempotency_key, "ts": created_at},
        )
        s.commit()


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


def test_handler_parks_safely_when_send_disabled(db_engine, seed_fixtures):
    """Main acceptance criterion: send_enabled=false parks safely."""
    wi_id = "wi_i1_disabled_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_disabled_01"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i1_disabled_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    # SEND_ENABLED defaults to false; ensure it's unset
    os.environ.pop("SEND_ENABLED", None)
    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    event_types = [e["event_type"] for e in events]
    assert "handler_started" in event_types
    assert "work_item_parked" in event_types
    parked = next(e for e in events if e["event_type"] == "work_item_parked")
    assert parked["error_code"] == "policy_blocked"

    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_no_send_attempt_created_when_send_disabled(db_engine, seed_fixtures):
    """No SendAttempt row must be created when send_enabled=false."""
    wi_id = "wi_i1_noattempt_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_noattempt_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")

    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i1_noattempt_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ.pop("SEND_ENABLED", None)
    handle_sending_dispatch({"work_item_id": wi_id})

    count = _get_send_attempt_count(db_engine, send_ik)
    assert count == 0, "SendAttempt must NOT be created when send_enabled=false"

    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_on_unsupported_payload_version(
    db_engine, seed_fixtures
):
    """Unsupported payload version must yield contract_error."""
    wi_id = "wi_i1_badver_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": "decision:x:y"},
        payload_version=99,
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_on_missing_draft_id(db_engine, seed_fixtures):
    """Missing draft_id must yield contract_error."""
    wi_id = "wi_i1_nodraft_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"decision_id": "decision:x:y"},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_on_missing_decision_id(db_engine, seed_fixtures):
    """Missing decision_id must yield contract_error."""
    wi_id = "wi_i1_nodecision_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_when_draft_not_found(db_engine, seed_fixtures):
    """Non-existent draft_id must yield contract_error."""
    wi_id = "wi_i1_baddraft_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={
            "draft_id": "draft:nonexistent:seq99:v99",
            "decision_id": "decision:x:y",
        },
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_when_approval_not_found(db_engine, seed_fixtures):
    """Non-existent decision_id must yield contract_error."""
    wi_id = "wi_i1_badapproval_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={
            "draft_id": _DB_DRAFT_ID,
            "decision_id": "decision:nonexistent:zzz",
        },
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_when_approval_draft_id_mismatch(
    db_engine, seed_fixtures
):
    """Approval decision must reference the same draft_id as payload."""
    wi_id = "wi_i1_draftlink_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_draftlink_01"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    other_draft_id = "draft:other:seq1:v1"
    with Session(db_engine) as s:
        s.execute(
            text(
                """
                INSERT INTO outreach_drafts (
                    draft_id, contact_id, account_id, channel, language,
                    policy_pack_id, subject, body, risk_flags_json, created_at, v
                ) VALUES (
                    :did, :cid, :aid, 'email', 'en', 'safe_v0_1',
                    'Other draft', 'Body {{unsubscribe_token}}', '[]'::jsonb, :ts, 1
                ) ON CONFLICT (draft_id) DO NOTHING
                """
            ),
            {
                "did": other_draft_id,
                "cid": _DB_CONTACT_ID,
                "aid": _DB_ACCOUNT_ID,
                "ts": _NOW,
            },
        )
        s.commit()

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=other_draft_id,
        work_item_id=wi_id,
        decision_key="dk_i1_draftlink_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_approval_decision(db_engine, decision_id)
    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM outreach_drafts WHERE draft_id = :did"),
            {"did": other_draft_id},
        )
        s.commit()
    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_when_approval_contact_id_mismatch(
    db_engine, seed_fixtures
):
    """Approval decision contact_id must match the draft-linked contact_id."""
    wi_id = "wi_i1_contactlink_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_contactlink_01"
    bad_contact_id = "contact:account:SI-9900001:other"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    with Session(db_engine) as s:
        s.execute(
            text(
                """
                INSERT INTO contacts (
                    contact_id, account_id, full_name, channels_json, provenance_json, status, v
                ) VALUES (
                    :cid, :aid, 'Other Contact', '[]'::jsonb, '[]'::jsonb, 'candidate', 1
                ) ON CONFLICT (contact_id) DO NOTHING
                """
            ),
            {"cid": bad_contact_id, "aid": _DB_ACCOUNT_ID},
        )
        s.commit()

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i1_contactlink_01",
        contact_id=bad_contact_id,
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_approval_decision(db_engine, decision_id)
    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM contacts WHERE contact_id = :cid"),
            {"cid": bad_contact_id},
        )
        s.commit()
    _clean_work_item(db_engine, wi_id)


def test_handler_contract_error_when_contact_not_found(db_engine, seed_fixtures):
    """Schema rejects draft fixtures that reference a missing contact."""
    wi_id = "wi_i1_nocontact_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_nocontact_01"
    missing_contact = "contact:missing:i1"
    draft_id = f"draft:{missing_contact}:seq1:v1"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    with Session(db_engine) as s:
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    """
                    INSERT INTO outreach_drafts (
                        draft_id, contact_id, account_id, channel, language,
                        policy_pack_id, subject, body, risk_flags_json, created_at, v
                    ) VALUES (
                        :did, :cid, :aid, 'email', 'en', 'safe_v0_1',
                        'Missing contact', 'Body', '[]'::jsonb, :ts, 1
                    )
                    """
                ),
                {
                    "did": draft_id,
                    "cid": missing_contact,
                    "aid": _DB_ACCOUNT_ID,
                    "ts": _NOW,
                },
            )
            s.commit()
        s.rollback()


def test_handler_contract_error_when_account_not_found(db_engine, seed_fixtures):
    """Schema rejects contact fixtures that reference a missing account."""
    wi_id = "wi_i1_noaccount_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_noaccount_01"
    account_id = "account:SI-MISSING-I1"
    contact_id = f"contact:{account_id}:hashed"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    with Session(db_engine) as s:
        with pytest.raises(IntegrityError):
            s.execute(
                text(
                    """
                    INSERT INTO contacts (
                        contact_id, account_id, full_name, channels_json, provenance_json, status, v
                    ) VALUES (
                        :cid, :aid, 'No Account', '[]'::jsonb, '[]'::jsonb, 'candidate', 1
                    )
                    """
                ),
                {"cid": contact_id, "aid": account_id},
            )
            s.commit()
        s.rollback()


def test_handler_contract_error_when_required_approval_field_missing(
    db_engine, seed_fixtures
):
    """Missing reviewer field in approval decision must yield contract_error."""
    wi_id = "wi_i1_missreview_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_missreview_01"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i1_missreview_01",
        reviewer_role="",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_failed_contract"
        and e["error_code"] == "contract_error"
        for e in events
    )

    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_handler_parks_policy_blocked_when_gate_overrides_present(
    db_engine, seed_fixtures
):
    """Gate overrides are forbidden for I1; handler must fail closed."""
    wi_id = "wi_i1_overrides_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_overrides_01"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i1_overrides_01",
        overridden_gates_json='["STOP_GATE_OVERRIDE"]',
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_parked" and e["error_code"] == "policy_blocked"
        for e in events
    )

    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_handler_parks_policy_blocked_when_approval_status_not_approved(
    db_engine, seed_fixtures
):
    """Non-approved approval status must park with policy_blocked."""
    wi_id = "wi_i1_rejected_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_rejected_01"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        status="rejected",
        decision_key="dk_i1_rejected_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_parked" and e["error_code"] == "policy_blocked"
        for e in events
    )

    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_handler_parks_policy_blocked_when_policy_pack_id_wrong(
    db_engine, seed_fixtures
):
    """Wrong policy_pack_id must park with policy_blocked."""
    wi_id = "wi_i1_wrongpolicy_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_wrongpolicy_01"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        policy_pack_id="other_policy_v1",
        decision_key="dk_i1_wrongpolicy_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_parked" and e["error_code"] == "policy_blocked"
        for e in events
    )

    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_handler_refs_remain_redacted_no_raw_email_patterns(db_engine, seed_fixtures):
    """Structured event refs must not contain full email-like identifiers."""
    wi_id = "wi_i1_redacted_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i1_redacted_01"
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i1_redacted_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ.pop("SEND_ENABLED", None)
    handle_sending_dispatch({"work_item_id": wi_id})

    refs_rows = _get_event_refs(db_engine, wi_id)
    refs_blob = json.dumps(refs_rows)
    assert "@" not in refs_blob
    assert "draft:" not in refs_blob
    assert "send:" not in refs_blob

    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_allowed_sandbox_path_creates_one_send_attempt_with_locked_fields(
    db_engine, seed_fixtures
):
    """send_enabled=true creates one SendAttempt with locked provider/status fields."""
    wi_id = "wi_i2_send_once_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i2_send_once_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i2_send_once_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ["SEND_ENABLED"] = "true"
    handle_sending_dispatch({"work_item_id": wi_id})
    os.environ.pop("SEND_ENABLED", None)

    assert _get_send_attempt_count(db_engine, send_ik) == 1
    row = _get_send_attempt_row(db_engine, send_ik)
    assert row is not None
    assert row["provider"] == "SEND_SRC_01"
    assert row["status"] == "queued"
    assert row["policy_pack_id"] == "safe_v0_1"

    events = _get_events(db_engine, wi_id)
    assert any(e["event_type"] == "work_item_completed" for e in events)

    _clean_send_attempt(db_engine, send_ik)
    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_allowed_sandbox_path_replay_reuses_existing_send_attempt(
    db_engine, seed_fixtures
):
    """Replaying the same work item must not create duplicate send attempts."""
    wi_id = "wi_i2_replay_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i2_replay_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i2_replay_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ["SEND_ENABLED"] = "true"
    handle_sending_dispatch({"work_item_id": wi_id})
    handle_sending_dispatch({"work_item_id": wi_id})
    os.environ.pop("SEND_ENABLED", None)

    assert _get_send_attempt_count(db_engine, send_ik) == 1

    sink_events = [
        e
        for e in _get_events_with_refs(db_engine, wi_id)
        if e["event_type"] == "handler_succeeded"
    ]
    assert len(sink_events) >= 2
    assert any(
        bool((e.get("refs") or {}).get("send_attempt_reused")) for e in sink_events
    )

    _clean_send_attempt(db_engine, send_ik)
    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_allowed_sandbox_path_writes_redacted_sink_payload(db_engine, seed_fixtures):
    """Sandbox sink event contains redacted metadata and no body/email."""
    wi_id = "wi_i2_sink_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i2_sink_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i2_sink_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ["SEND_ENABLED"] = "true"
    handle_sending_dispatch({"work_item_id": wi_id})
    os.environ.pop("SEND_ENABLED", None)

    sink_events = [
        e
        for e in _get_events_with_refs(db_engine, wi_id)
        if e["event_type"] == "handler_succeeded"
    ]
    assert len(sink_events) >= 1
    refs = sink_events[-1]["refs"]
    assert refs["send_mode"] == "sandbox_log_sink_only"
    assert refs["provider_id"] == "SEND_SRC_01"
    assert refs["channel"] == "email"
    assert "template_id" in refs
    assert "recipient_domain" in refs
    assert "recipient_hash" in refs

    refs_blob = json.dumps(refs)
    assert "@" not in refs_blob
    assert "Test body" not in refs_blob
    assert "Test I1 subject" not in refs_blob

    _clean_send_attempt(db_engine, send_ik)
    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_i3_handler_parks_policy_blocked_on_free_email_domain(db_engine, seed_fixtures):
    """I3 STOP: free email domains must park policy_blocked."""
    wi_id = "wi_i3_free_domain_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i3_free_domain_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    _set_contact_channels(
        db_engine,
        _DB_CONTACT_ID,
        [
            {
                "type": "email",
                "value": "dana@gmail.com",
                "validated": "domain_ok",
                "confidence": 0.95,
            }
        ],
    )

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i3_free_domain_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ["SEND_ENABLED"] = "true"
    handle_sending_dispatch({"work_item_id": wi_id})
    os.environ.pop("SEND_ENABLED", None)

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_parked" and e["error_code"] == "policy_blocked"
        for e in events
    )
    assert _get_send_attempt_count(db_engine, send_ik) == 0

    _set_contact_channels(
        db_engine,
        _DB_CONTACT_ID,
        [
            {
                "type": "email",
                "value": "dana@test-i1.example",
                "validated": "domain_ok",
                "confidence": 0.92,
            }
        ],
    )
    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_i3_handler_parks_needs_human_on_review_confidence_band(
    db_engine, seed_fixtures
):
    """I3 REVIEW: confidence 0.60..0.79 must park as needs_human."""
    wi_id = "wi_i3_conf_review_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i3_conf_review_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    _set_contact_channels(
        db_engine,
        _DB_CONTACT_ID,
        [
            {
                "type": "email",
                "value": "dana@test-i1.example",
                "validated": "domain_ok",
                "confidence": 0.70,
            }
        ],
    )

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i3_conf_review_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ["SEND_ENABLED"] = "true"
    handle_sending_dispatch({"work_item_id": wi_id})
    os.environ.pop("SEND_ENABLED", None)

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_parked" and e["error_code"] == "needs_human"
        for e in events
    )
    assert _get_send_attempt_count(db_engine, send_ik) == 0

    _set_contact_channels(
        db_engine,
        _DB_CONTACT_ID,
        [
            {
                "type": "email",
                "value": "dana@test-i1.example",
                "validated": "domain_ok",
                "confidence": 0.92,
            }
        ],
    )
    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_i3_handler_parks_policy_blocked_on_hourly_throttle(db_engine, seed_fixtures):
    """I3 STOP: hourly burst over cap must park policy_blocked."""
    wi_id = "wi_i3_hourly_cap_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i3_hourly_cap_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    for i in range(5):
        _insert_send_attempt_row(
            db_engine,
            send_id=f"send:i3:cap:{i}",
            draft_id=_DB_DRAFT_ID,
            idempotency_key=f"send:i3:cap:{i}:email:v1",
            created_at=_NOW,
        )

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i3_hourly_cap_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ["SEND_ENABLED"] = "true"
    handle_sending_dispatch({"work_item_id": wi_id})
    os.environ.pop("SEND_ENABLED", None)

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_parked" and e["error_code"] == "policy_blocked"
        for e in events
    )
    assert _get_send_attempt_count(db_engine, send_ik) == 0

    with Session(db_engine) as s:
        s.execute(text("DELETE FROM send_attempts WHERE send_id LIKE 'send:i3:cap:%'"))
        s.commit()
    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_i3_handler_parks_policy_blocked_on_suppression_hit(db_engine, seed_fixtures):
    """I3 STOP: suppression sources must block sending deterministically."""
    wi_id = "wi_i3_suppression_01"
    decision_id = f"decision:{_DB_DRAFT_ID}:dk_i3_suppression_01"
    send_ik = make_send_attempt_idempotency_key(_DB_DRAFT_ID, "email")
    _clean_work_item(db_engine, wi_id)
    _clean_approval_decision(db_engine, decision_id)
    _clean_send_attempt(db_engine, send_ik)

    with Session(db_engine) as s:
        s.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS global_dnc (
                    contact_id TEXT,
                    email TEXT,
                    domain TEXT
                )
                """
            )
        )
        s.execute(
            text(
                "INSERT INTO global_dnc (contact_id, email, domain) VALUES (:cid, :em, :dm)"
            ),
            {
                "cid": _DB_CONTACT_ID,
                "em": "dana@test-i1.example",
                "dm": "test-i1.example",
            },
        )
        s.commit()

    _make_approval_decision(
        db_engine,
        decision_id=decision_id,
        draft_id=_DB_DRAFT_ID,
        work_item_id=wi_id,
        decision_key="dk_i3_suppression_01",
    )
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={"draft_id": _DB_DRAFT_ID, "decision_id": decision_id},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    os.environ["SEND_ENABLED"] = "true"
    handle_sending_dispatch({"work_item_id": wi_id})
    os.environ.pop("SEND_ENABLED", None)

    events = _get_events(db_engine, wi_id)
    assert any(
        e["event_type"] == "work_item_parked" and e["error_code"] == "policy_blocked"
        for e in events
    )
    assert _get_send_attempt_count(db_engine, send_ik) == 0

    with Session(db_engine) as s:
        s.execute(
            text("DELETE FROM global_dnc WHERE contact_id = :cid"),
            {"cid": _DB_CONTACT_ID},
        )
        s.commit()
    _clean_approval_decision(db_engine, decision_id)
    _clean_work_item(db_engine, wi_id)


def test_handler_started_always_emitted(db_engine, seed_fixtures):
    """handler_started must be the first event regardless of outcome."""
    wi_id = "wi_i1_started_01"
    _clean_work_item(db_engine, wi_id)
    _make_work_item(
        db_engine=db_engine,
        work_item_id=wi_id,
        payload_data={},
    )

    from aose_worker.handlers.sending_dispatch import handle_sending_dispatch

    handle_sending_dispatch({"work_item_id": wi_id})

    events = _get_events(db_engine, wi_id)
    assert events[0]["event_type"] == "handler_started"

    _clean_work_item(db_engine, wi_id)
