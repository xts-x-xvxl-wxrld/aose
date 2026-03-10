"""
Tests for Epic B9: ApprovalDecision + SendAttempt persistence.

Requires a live Postgres instance (DATABASE_URL env var).
Tests are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aose_api.ids import (
    make_contact_id,
    make_decision_id,
    make_decision_key,
    make_draft_id,
    make_send_id,
    make_send_idempotency_key,
)
from aose_api.models import (
    Account,
    ApprovalDecision,
    Contact,
    OutreachDraft,
    SendAttempt,
    validate_approval_status,
    validate_send_provider,
)


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 8, 16, 0, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "account:SI-9890001"
CONTACT_ID = make_contact_id(account_id=ACCOUNT_ID, email="carol.white@example.si")
WORK_ITEM_ID = "wi_b9_test_approval"
DRAFT_ID = make_draft_id(contact_id=CONTACT_ID, sequence_no=1, variant_no=1)
POLICY_PACK_ID = "safe_v0_1"
ACTION_TYPE = "approve_send"  # B9 assumption: narrowest conservative value

SAMPLE_DECISION_KWARGS = dict(
    work_item_id=WORK_ITEM_ID,
    contact_id=CONTACT_ID,
    action_type=ACTION_TYPE,
    policy_pack_id=POLICY_PACK_ID,
    draft_id=DRAFT_ID,
)

DECISION_KEY = make_decision_key(**SAMPLE_DECISION_KWARGS)
DECISION_ID = make_decision_id(draft_id=DRAFT_ID, decision_key=DECISION_KEY)

SAMPLE_DECISION = dict(
    decision_id=DECISION_ID,
    decision_key=DECISION_KEY,
    draft_id=DRAFT_ID,
    work_item_id=WORK_ITEM_ID,
    contact_id=CONTACT_ID,
    action_type=ACTION_TYPE,
    status="approved",
    reviewer="human:TBD",
    reviewer_id="reviewer:op-001",
    reviewer_role="operator",
    notes=None,
    overridden_gates_json=[],
    policy_pack_id=POLICY_PACK_ID,
    decided_at=NOW,
    v=1,
)

SEND_ID = make_send_id(draft_id=DRAFT_ID, channel="email")
SEND_IDEMPOTENCY_KEY = make_send_idempotency_key(draft_id=DRAFT_ID, channel="email")

SAMPLE_SEND = dict(
    send_id=SEND_ID,
    draft_id=DRAFT_ID,
    decision_id=None,
    channel="email",
    provider="SEND_SRC_01",
    status="queued",
    provider_message_id=None,
    idempotency_key=SEND_IDEMPOTENCY_KEY,
    policy_pack_id=POLICY_PACK_ID,
    created_at=NOW,
    v=1,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def db_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping DB tests")
    engine = create_engine(_sa_url(url))
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def seed_fixtures(db_engine):
    """Ensure account, contact, work_item, and draft exist for B9 tests."""
    from aose_api.models import WorkItem

    with Session(db_engine) as s:
        if s.get(Account, ACCOUNT_ID) is None:
            s.add(
                Account(
                    account_id=ACCOUNT_ID,
                    name="Test Corp B9",
                    domain=None,
                    country="SI",
                    provenance=[],
                    evidence_ids=[],
                    confidence=0.9,
                    status="candidate",
                    v=1,
                )
            )
        if s.get(Contact, CONTACT_ID) is None:
            s.add(
                Contact(
                    contact_id=CONTACT_ID,
                    account_id=ACCOUNT_ID,
                    full_name="Carol White",
                    role_json=None,
                    channels_json=[],
                    provenance_json=[],
                    status="candidate",
                    v=1,
                )
            )
        if s.get(WorkItem, WORK_ITEM_ID) is None:
            s.add(
                WorkItem(
                    work_item_id=WORK_ITEM_ID,
                    entity_ref_type="account",
                    entity_ref_id=ACCOUNT_ID,
                    stage="approval_request",
                    payload_json={"v": 1, "data": {}},
                    payload_version=1,
                    attempt_budget_remaining=3,
                    attempt_budget_policy="standard",
                    idempotency_key=f"approval:{DRAFT_ID}:v1",
                    trace_run_id="run_b9_test",
                    trace_parent_work_item_id=None,
                    trace_correlation_id=f"corr:{ACCOUNT_ID}",
                    trace_policy_pack_id=POLICY_PACK_ID,
                    created_at=NOW,
                )
            )
        if s.get(OutreachDraft, DRAFT_ID) is None:
            s.add(
                OutreachDraft(
                    draft_id=DRAFT_ID,
                    contact_id=CONTACT_ID,
                    account_id=ACCOUNT_ID,
                    channel="email",
                    language="en",
                    policy_pack_id=POLICY_PACK_ID,
                    subject="Quick question",
                    body="Hi Carol, ...",
                    risk_flags_json=[],
                    created_at=NOW,
                    v=1,
                )
            )
        s.commit()
    yield


@pytest.fixture
def session(db_engine, seed_fixtures):
    with Session(db_engine) as s:
        yield s


def _clean_decision(session: Session, *decision_ids: str) -> None:
    for did in decision_ids:
        # Remove send_attempts referencing this decision first
        for sa_row in (
            session.query(SendAttempt).filter(SendAttempt.decision_id == did).all()
        ):
            session.delete(sa_row)
        row = session.get(ApprovalDecision, did)
        if row:
            session.delete(row)
    session.commit()


def _clean_send(session: Session, *send_ids: str) -> None:
    for sid in send_ids:
        row = session.get(SendAttempt, sid)
        if row:
            session.delete(row)
    session.commit()


# ---------------------------------------------------------------------------
# Pure ID formula tests (no DB)
# ---------------------------------------------------------------------------


def test_decision_key_deterministic():
    k1 = make_decision_key(**SAMPLE_DECISION_KWARGS)
    k2 = make_decision_key(**SAMPLE_DECISION_KWARGS)
    assert k1 == k2


def test_decision_key_different_inputs_differ():
    k1 = make_decision_key(**SAMPLE_DECISION_KWARGS)
    k2 = make_decision_key(**{**SAMPLE_DECISION_KWARGS, "action_type": "other_action"})
    assert k1 != k2


def test_decision_id_follows_locked_formula():
    dk = make_decision_key(**SAMPLE_DECISION_KWARGS)
    did = make_decision_id(draft_id=DRAFT_ID, decision_key=dk)
    assert did == f"decision:{DRAFT_ID}:{dk}"


def test_send_id_follows_locked_formula():
    sid = make_send_id(draft_id=DRAFT_ID, channel="email")
    assert sid == f"send:{DRAFT_ID}:email"


def test_send_idempotency_key_follows_locked_formula():
    ik = make_send_idempotency_key(draft_id=DRAFT_ID, channel="email")
    assert ik == f"send:{DRAFT_ID}:email:v1"


def test_different_channels_produce_different_send_ids():
    sid_email = make_send_id(draft_id=DRAFT_ID, channel="email")
    sid_linkedin = make_send_id(draft_id=DRAFT_ID, channel="linkedin")
    assert sid_email != sid_linkedin


# ---------------------------------------------------------------------------
# Pure validator tests (no DB)
# ---------------------------------------------------------------------------


def test_validate_approval_status_accepts_all_locked_values():
    for status in ("approved", "rejected", "needs_rewrite", "needs_more_evidence"):
        validate_approval_status(status)


def test_validate_approval_status_rejects_unlocked():
    with pytest.raises(ValueError):
        validate_approval_status("pending")


def test_validate_approval_status_rejects_invented():
    with pytest.raises(ValueError):
        validate_approval_status("escalated")


def test_validate_send_provider_accepts_send_src_01():
    validate_send_provider("SEND_SRC_01")


def test_validate_send_provider_rejects_invented():
    with pytest.raises(ValueError):
        validate_send_provider("sendgrid")


# ---------------------------------------------------------------------------
# DB: ApprovalDecision
# ---------------------------------------------------------------------------


def test_decision_create_and_read(session):
    _clean_decision(session, DECISION_ID)

    decision = ApprovalDecision(**SAMPLE_DECISION)
    session.add(decision)
    session.commit()
    session.expire(decision)

    found = session.get(ApprovalDecision, DECISION_ID)
    assert found is not None
    assert found.decision_id == DECISION_ID
    assert found.decision_key == DECISION_KEY
    assert found.draft_id == DRAFT_ID
    assert found.status == "approved"
    assert found.reviewer_id == "reviewer:op-001"
    assert found.reviewer_role == "operator"
    assert found.policy_pack_id == POLICY_PACK_ID
    assert found.created_at is not None

    _clean_decision(session, DECISION_ID)


def test_decision_status_db_constraint_rejects_invalid(session):
    bad_id = make_decision_id(
        draft_id=DRAFT_ID,
        decision_key=make_decision_key(
            **{**SAMPLE_DECISION_KWARGS, "action_type": "bad_status_test"}
        ),
    )
    _clean_decision(session, bad_id)

    bad_key = make_decision_key(
        **{**SAMPLE_DECISION_KWARGS, "action_type": "bad_status_test"}
    )
    decision = ApprovalDecision(
        **{
            **SAMPLE_DECISION,
            "decision_id": bad_id,
            "decision_key": bad_key,
            "status": "pending",
        }
    )
    session.add(decision)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_decision_overridden_gates_roundtrip(session):
    _clean_decision(session, DECISION_ID)

    gates = [{"gate": "risk_threshold", "reason": "operator override"}]
    decision = ApprovalDecision(**{**SAMPLE_DECISION, "overridden_gates_json": gates})
    session.add(decision)
    session.commit()
    session.expire(decision)

    found = session.get(ApprovalDecision, DECISION_ID)
    assert found.overridden_gates_json == gates

    _clean_decision(session, DECISION_ID)


def test_decision_notes_nullable(session):
    _clean_decision(session, DECISION_ID)

    decision = ApprovalDecision(**{**SAMPLE_DECISION, "notes": None})
    session.add(decision)
    session.commit()
    session.expire(decision)

    found = session.get(ApprovalDecision, DECISION_ID)
    assert found.notes is None

    _clean_decision(session, DECISION_ID)


def test_replay_same_decision_key_rejected(session):
    _clean_decision(session, DECISION_ID)

    d1 = ApprovalDecision(**SAMPLE_DECISION)
    session.add(d1)
    session.commit()

    # Same decision_key but different decision_id would violate unique(decision_key)
    alt_id = f"{DECISION_ID}:alt"
    with Session(session.bind) as s2:
        d2 = ApprovalDecision(**{**SAMPLE_DECISION, "decision_id": alt_id})
        s2.add(d2)
        with pytest.raises(IntegrityError):
            s2.commit()

    rows = (
        session.query(ApprovalDecision)
        .filter(ApprovalDecision.decision_key == DECISION_KEY)
        .all()
    )
    assert len(rows) == 1

    _clean_decision(session, DECISION_ID)


def test_all_locked_statuses_accepted(session):
    for status in ("approved", "rejected", "needs_rewrite", "needs_more_evidence"):
        dk = make_decision_key(
            **{**SAMPLE_DECISION_KWARGS, "action_type": f"test_{status}"}
        )
        did = make_decision_id(draft_id=DRAFT_ID, decision_key=dk)
        _clean_decision(session, did)

        d = ApprovalDecision(
            **{
                **SAMPLE_DECISION,
                "decision_id": did,
                "decision_key": dk,
                "status": status,
            }
        )
        session.add(d)
        session.commit()
        _clean_decision(session, did)


# ---------------------------------------------------------------------------
# DB: SendAttempt
# ---------------------------------------------------------------------------


def test_send_attempt_create_and_read(session):
    _clean_send(session, SEND_ID)

    sa = SendAttempt(**SAMPLE_SEND)
    session.add(sa)
    session.commit()
    session.expire(sa)

    found = session.get(SendAttempt, SEND_ID)
    assert found is not None
    assert found.send_id == SEND_ID
    assert found.draft_id == DRAFT_ID
    assert found.channel == "email"
    assert found.provider == "SEND_SRC_01"
    assert found.status == "queued"
    assert found.idempotency_key == SEND_IDEMPOTENCY_KEY
    assert found.provider_message_id is None

    _clean_send(session, SEND_ID)


def test_send_attempt_linked_to_decision(session):
    _clean_decision(session, DECISION_ID)
    _clean_send(session, SEND_ID)

    session.add(ApprovalDecision(**SAMPLE_DECISION))
    session.flush()

    sa = SendAttempt(**{**SAMPLE_SEND, "decision_id": DECISION_ID})
    session.add(sa)
    session.commit()
    session.expire(sa)

    found = session.get(SendAttempt, SEND_ID)
    assert found.decision_id == DECISION_ID

    _clean_send(session, SEND_ID)
    _clean_decision(session, DECISION_ID)


def test_replay_same_idempotency_key_rejected(session):
    _clean_send(session, SEND_ID)

    sa1 = SendAttempt(**SAMPLE_SEND)
    session.add(sa1)
    session.commit()

    alt_send_id = f"{SEND_ID}:alt"
    with Session(session.bind) as s2:
        sa2 = SendAttempt(**{**SAMPLE_SEND, "send_id": alt_send_id})
        s2.add(sa2)
        with pytest.raises(IntegrityError):
            s2.commit()

    rows = (
        session.query(SendAttempt)
        .filter(SendAttempt.idempotency_key == SEND_IDEMPOTENCY_KEY)
        .all()
    )
    assert len(rows) == 1

    _clean_send(session, SEND_ID)


def test_no_real_provider_side_effects():
    """Verify no network calls or real send side effects exist in this module."""
    import aose_api.models as m

    # The models module must not import any send-provider SDK
    assert not hasattr(m, "sendgrid")
    assert not hasattr(m, "smtp")
    assert not hasattr(m, "boto3")


# ---------------------------------------------------------------------------
# Schema inspection tests
# ---------------------------------------------------------------------------


def test_approval_decisions_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "approval_decisions" in inspector.get_table_names()


def test_send_attempts_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "send_attempts" in inspector.get_table_names()


def test_required_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    ad_idx = {i["name"] for i in inspector.get_indexes("approval_decisions")}
    sa_idx = {i["name"] for i in inspector.get_indexes("send_attempts")}
    assert "ix_approval_decisions_decision_key" in ad_idx
    assert "ix_approval_decisions_draft_id" in ad_idx
    assert "ix_approval_decisions_contact_id" in ad_idx
    assert "ix_approval_decisions_decided_at" in ad_idx
    assert "ix_send_attempts_idempotency_key" in sa_idx
    assert "ix_send_attempts_draft_id" in sa_idx
    assert "ix_send_attempts_decision_id" in sa_idx
    assert "ix_send_attempts_created_at" in sa_idx


def test_unique_constraints_exist(db_engine):
    inspector = inspect(db_engine)
    ad_uq = {u["name"] for u in inspector.get_unique_constraints("approval_decisions")}
    sa_uq = {u["name"] for u in inspector.get_unique_constraints("send_attempts")}
    assert "uq_approval_decisions_decision_key" in ad_uq
    assert "uq_send_attempts_idempotency_key" in sa_uq


def test_status_check_constraint_exists(db_engine):
    inspector = inspect(db_engine)
    constraints = {
        c["name"] for c in inspector.get_check_constraints("approval_decisions")
    }
    assert "ck_approval_decisions_status" in constraints
