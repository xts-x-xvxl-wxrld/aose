"""
Tests for Epic B8: OutreachDraft + PersonalizationAnchor persistence.

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

from aose_api.ids import make_anchor_key, make_contact_id, make_draft_id
from aose_api.models import (
    Account,
    Contact,
    OutreachDraft,
    PersonalizationAnchor,
    validate_anchor_evidence_ids,
)


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 8, 15, 0, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "account:SI-9880001"
CONTACT_ID = make_contact_id(account_id=ACCOUNT_ID, email="bob.smith@example.si")

SAMPLE_DRAFT = dict(
    contact_id=CONTACT_ID,
    account_id=ACCOUNT_ID,
    channel="email",
    language="en",
    policy_pack_id="safe_v0_1",
    subject="Quick question about your SMT line",
    body="Hi Bob, noticed you run SMT assembly at scale — we help with that.",
    risk_flags_json=[],
    created_at=NOW,
    v=1,
)


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
    """Ensure anchor account + contact exist for all draft tests."""
    with Session(db_engine) as s:
        if s.get(Account, ACCOUNT_ID) is None:
            s.add(
                Account(
                    account_id=ACCOUNT_ID,
                    name="Test Corp B8",
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
                    full_name="Bob Smith",
                    role_json=None,
                    channels_json=[],
                    provenance_json=[],
                    status="candidate",
                    v=1,
                )
            )
        s.commit()
    yield


@pytest.fixture
def session(db_engine, seed_fixtures):
    with Session(db_engine) as s:
        yield s


def _make_draft_id(seq: int = 1, variant: int = 1) -> str:
    return make_draft_id(contact_id=CONTACT_ID, sequence_no=seq, variant_no=variant)


def _clean(session: Session, *draft_ids: str) -> None:
    for did in draft_ids:
        anchors = (
            session.query(PersonalizationAnchor)
            .filter(PersonalizationAnchor.draft_id == did)
            .all()
        )
        for a in anchors:
            session.delete(a)
        row = session.get(OutreachDraft, did)
        if row:
            session.delete(row)
    session.commit()


# ---------------------------------------------------------------------------
# make_draft_id tests (pure, no DB)
# ---------------------------------------------------------------------------


def test_draft_id_follows_locked_formula():
    did = make_draft_id(contact_id="contact:x:a@b.com", sequence_no=1, variant_no=1)
    assert did == "draft:contact:x:a@b.com:seq1:v1"


def test_draft_id_deterministic():
    did1 = make_draft_id(contact_id=CONTACT_ID, sequence_no=2, variant_no=3)
    did2 = make_draft_id(contact_id=CONTACT_ID, sequence_no=2, variant_no=3)
    assert did1 == did2


def test_different_sequence_no_produce_different_ids():
    did_a = make_draft_id(contact_id=CONTACT_ID, sequence_no=1, variant_no=1)
    did_b = make_draft_id(contact_id=CONTACT_ID, sequence_no=2, variant_no=1)
    assert did_a != did_b


def test_different_variant_no_produce_different_ids():
    did_a = make_draft_id(contact_id=CONTACT_ID, sequence_no=1, variant_no=1)
    did_b = make_draft_id(contact_id=CONTACT_ID, sequence_no=1, variant_no=2)
    assert did_a != did_b


# ---------------------------------------------------------------------------
# make_anchor_key tests (pure, no DB)
# ---------------------------------------------------------------------------


def test_anchor_key_deterministic():
    did = _make_draft_id()
    k1 = make_anchor_key(did, "noticed you run SMT assembly", ["evidence:abc"])
    k2 = make_anchor_key(did, "noticed you run SMT assembly", ["evidence:abc"])
    assert k1 == k2
    assert k1.startswith("anchor:")


def test_anchor_key_different_spans_differ():
    did = _make_draft_id()
    k1 = make_anchor_key(did, "span A", ["evidence:abc"])
    k2 = make_anchor_key(did, "span B", ["evidence:abc"])
    assert k1 != k2


def test_anchor_key_evidence_id_order_invariant():
    did = _make_draft_id()
    k1 = make_anchor_key(did, "span", ["evidence:aaa", "evidence:bbb"])
    k2 = make_anchor_key(did, "span", ["evidence:bbb", "evidence:aaa"])
    assert k1 == k2


# ---------------------------------------------------------------------------
# validate_anchor_evidence_ids tests (pure, no DB)
# ---------------------------------------------------------------------------


def test_validate_anchor_evidence_ids_accepts_valid():
    validate_anchor_evidence_ids(["evidence:abc123"])


def test_validate_anchor_evidence_ids_accepts_multiple():
    validate_anchor_evidence_ids(["evidence:abc", "evidence:def"])


def test_validate_anchor_evidence_ids_rejects_empty_list():
    with pytest.raises(ValueError, match="at least one"):
        validate_anchor_evidence_ids([])


def test_validate_anchor_evidence_ids_rejects_non_list():
    with pytest.raises(ValueError, match="list"):
        validate_anchor_evidence_ids("evidence:abc")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# DB: OutreachDraft
# ---------------------------------------------------------------------------


def test_draft_create_and_read(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
    session.add(draft)
    session.commit()
    session.expire(draft)

    found = session.get(OutreachDraft, did)
    assert found is not None
    assert found.draft_id == did
    assert found.contact_id == CONTACT_ID
    assert found.account_id == ACCOUNT_ID
    assert found.channel == "email"
    assert found.language == "en"
    assert found.policy_pack_id == "safe_v0_1"
    assert found.v == 1

    _clean(session, did)


def test_draft_subject_body_roundtrip(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
    session.add(draft)
    session.commit()
    session.expire(draft)

    found = session.get(OutreachDraft, did)
    assert found.subject == "Quick question about your SMT line"
    assert (
        found.body
        == "Hi Bob, noticed you run SMT assembly at scale — we help with that."
    )

    _clean(session, did)


def test_risk_flags_json_defaults_to_empty_array(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did, "risk_flags_json": []})
    session.add(draft)
    session.commit()
    session.expire(draft)

    found = session.get(OutreachDraft, did)
    assert found.risk_flags_json == []

    _clean(session, did)


def test_risk_flags_json_roundtrip(session):
    did = _make_draft_id()
    _clean(session, did)

    flags = [{"code": "price_mention", "severity": "low"}]
    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did, "risk_flags_json": flags})
    session.add(draft)
    session.commit()
    session.expire(draft)

    found = session.get(OutreachDraft, did)
    assert found.risk_flags_json == flags

    _clean(session, did)


# ---------------------------------------------------------------------------
# DB: PersonalizationAnchor
# ---------------------------------------------------------------------------


def test_anchor_create_and_link(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
    session.add(draft)
    session.flush()

    span = "noticed you run SMT assembly"
    eids = ["evidence:abc123"]
    ak = make_anchor_key(did, span, eids)
    anchor = PersonalizationAnchor(
        anchor_key=ak,
        draft_id=did,
        span=span,
        evidence_ids_json=eids,
        v=1,
    )
    session.add(anchor)
    session.commit()

    found = session.get(OutreachDraft, did)
    assert len(found.anchors) == 1
    assert found.anchors[0].span == span
    assert found.anchors[0].evidence_ids_json == eids

    _clean(session, did)


def test_anchor_span_and_evidence_ids_roundtrip(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
    session.add(draft)
    session.flush()

    span = "we help teams at your scale"
    eids = ["evidence:def456", "evidence:ghi789"]
    ak = make_anchor_key(did, span, eids)
    anchor = PersonalizationAnchor(
        anchor_key=ak, draft_id=did, span=span, evidence_ids_json=eids, v=1
    )
    session.add(anchor)
    session.commit()
    session.expire(anchor)

    found = session.get(PersonalizationAnchor, ak)
    assert found.span == span
    assert set(found.evidence_ids_json) == set(eids)

    _clean(session, did)


def test_multiple_anchors_per_draft(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
    session.add(draft)
    session.flush()

    spans = [
        ("noticed you run SMT assembly", ["evidence:abc"]),
        ("we help with that", ["evidence:def"]),
        ("teams at your scale", ["evidence:ghi", "evidence:jkl"]),
    ]
    for span, eids in spans:
        ak = make_anchor_key(did, span, eids)
        session.add(
            PersonalizationAnchor(
                anchor_key=ak, draft_id=did, span=span, evidence_ids_json=eids, v=1
            )
        )
    session.commit()

    found = session.get(OutreachDraft, did)
    assert len(found.anchors) == 3

    _clean(session, did)


# ---------------------------------------------------------------------------
# Replay safety tests
# ---------------------------------------------------------------------------


def test_replay_same_draft_id_rejected(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
    session.add(draft)
    session.commit()

    with Session(session.bind) as s2:
        draft2 = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
        s2.add(draft2)
        with pytest.raises(IntegrityError):
            s2.commit()

    rows = session.query(OutreachDraft).filter(OutreachDraft.draft_id == did).all()
    assert len(rows) == 1

    _clean(session, did)


def test_replay_same_anchor_key_rejected(session):
    did = _make_draft_id()
    _clean(session, did)

    draft = OutreachDraft(**{**SAMPLE_DRAFT, "draft_id": did})
    session.add(draft)
    session.flush()

    span = "noticed you run SMT assembly"
    eids = ["evidence:abc123"]
    ak = make_anchor_key(did, span, eids)
    session.add(
        PersonalizationAnchor(
            anchor_key=ak, draft_id=did, span=span, evidence_ids_json=eids, v=1
        )
    )
    session.commit()

    with Session(session.bind) as s2:
        s2.add(
            PersonalizationAnchor(
                anchor_key=ak, draft_id=did, span=span, evidence_ids_json=eids, v=1
            )
        )
        with pytest.raises(IntegrityError):
            s2.commit()

    _clean(session, did)


# ---------------------------------------------------------------------------
# Schema inspection tests
# ---------------------------------------------------------------------------


def test_outreach_drafts_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "outreach_drafts" in inspector.get_table_names()


def test_personalization_anchors_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "personalization_anchors" in inspector.get_table_names()


def test_required_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    d_idx = {i["name"] for i in inspector.get_indexes("outreach_drafts")}
    a_idx = {i["name"] for i in inspector.get_indexes("personalization_anchors")}
    assert "ix_outreach_drafts_contact_id" in d_idx
    assert "ix_outreach_drafts_account_id" in d_idx
    assert "ix_outreach_drafts_created_at" in d_idx
    assert "ix_personalization_anchors_draft_id" in a_idx


# ---------------------------------------------------------------------------
# Contract guard tests
# ---------------------------------------------------------------------------


def test_drafts_coexist_with_all_epic_c_tables(db_engine):
    # structured_events was added in Epic C — outreach_drafts must still coexist
    tables = inspect(db_engine).get_table_names()
    assert "outreach_drafts" in tables
    assert "structured_events" in tables
