"""
Tests for Epic B5: Evidence + EvidenceContent persistence.

Requires a live Postgres instance (DATABASE_URL env var).
Tests are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aose_api.ids import make_evidence_id
from aose_api.models import Evidence, EvidenceContent


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


def _content_id(content_hash: str) -> str:
    return f"content:{content_hash}"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 8, 12, 0, 0, tzinfo=timezone.utc)

SAMPLE_EVIDENCE = dict(
    source_type="web_page",
    canonical_url="https://example.com/about",
    captured_at=NOW,
    snippet="Example Corp is a leading provider of widgets.",
    claim_frame="company_description",
    source_provider="web_scraper",
    source_ref="scrape-001",
    observed_at=NOW,
    confidence=0.85,
    provenance_json=[{"source": "web_scraper", "captured_at": "2026-03-08"}],
    content_ref_id=None,
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


@pytest.fixture
def session(db_engine):
    with Session(db_engine) as s:
        yield s


def _clean_evidence(session: Session, *evidence_ids: str) -> None:
    for eid in evidence_ids:
        row = session.get(Evidence, eid)
        if row:
            session.delete(row)
    session.commit()


def _clean_content(session: Session, *content_ids: str) -> None:
    for cid in content_ids:
        row = session.get(EvidenceContent, cid)
        if row:
            session.delete(row)
    session.commit()


def _make_eid(snippet: str = "Example Corp is a leading provider of widgets.") -> str:
    return make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/about",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text=snippet,
    )


# ---------------------------------------------------------------------------
# Evidence ID determinism tests (pure, no DB)
# ---------------------------------------------------------------------------


def test_evidence_id_deterministic():
    eid1 = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/about",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="Some snippet.",
    )
    eid2 = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/about",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="Some snippet.",
    )
    assert eid1 == eid2
    assert eid1.startswith("evidence:")


def test_different_snippets_produce_different_ids():
    eid_a = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/about",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="Snippet A",
    )
    eid_b = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/about",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="Snippet B",
    )
    assert eid_a != eid_b


def test_empty_snippet_hashes_deterministically():
    eid1 = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text=None,
    )
    eid2 = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text=None,
    )
    assert eid1 == eid2
    assert eid1.startswith("evidence:")


def test_none_and_empty_string_snippet_produce_same_id():
    eid_none = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text=None,
    )
    eid_empty = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="",
    )
    # Both are deterministic; None and "" produce the same snippet_hash
    # because _sha256("") is used for both None and "". Document the contract.
    assert eid_none == eid_empty  # locked by contract: None -> ""


# ---------------------------------------------------------------------------
# Schema / model tests
# ---------------------------------------------------------------------------


def test_evidence_pointer_only(session):
    """Evidence must be storable without an EvidenceContent row."""
    eid = _make_eid()
    _clean_evidence(session, eid)

    ev = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid})
    session.add(ev)
    session.commit()
    session.expire(ev)

    found = session.get(Evidence, eid)
    assert found is not None
    assert found.evidence_id == eid
    assert found.content_ref_id is None

    _clean_evidence(session, eid)


def test_evidence_url_snippet_claim_frame_roundtrip(session):
    eid = _make_eid()
    _clean_evidence(session, eid)

    ev = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid})
    session.add(ev)
    session.commit()
    session.expire(ev)

    found = session.get(Evidence, eid)
    assert found.canonical_url == "https://example.com/about"
    assert found.snippet == "Example Corp is a leading provider of widgets."
    assert found.claim_frame == "company_description"

    _clean_evidence(session, eid)


def test_evidence_provenance_json_roundtrip(session):
    eid = _make_eid()
    _clean_evidence(session, eid)

    provenance = [{"source": "web_scraper", "captured_at": "2026-03-08", "ref": "x"}]
    ev = Evidence(
        **{**SAMPLE_EVIDENCE, "evidence_id": eid, "provenance_json": provenance}
    )
    session.add(ev)
    session.commit()
    session.expire(ev)

    found = session.get(Evidence, eid)
    assert found.provenance_json == provenance

    _clean_evidence(session, eid)


def test_evidence_content_create_and_link(session):
    content_hash = _sha256("Full page HTML content here.")
    cid = _content_id(content_hash)
    eid = _make_eid()
    _clean_evidence(session, eid)
    _clean_content(session, cid)

    content = EvidenceContent(
        evidence_content_id=cid,
        content_hash=content_hash,
        kind="html",
        text="Full page HTML content here.",
        raw_ref_kind=None,
        raw_ref_id=None,
        captured_at=NOW,
        v=1,
    )
    session.add(content)
    session.flush()

    ev = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid, "content_ref_id": cid})
    session.add(ev)
    session.commit()
    session.expire(ev)

    found = session.get(Evidence, eid)
    assert found.content_ref_id == cid

    content_found = session.get(EvidenceContent, cid)
    assert content_found.kind == "html"
    assert content_found.text == "Full page HTML content here."

    _clean_evidence(session, eid)
    _clean_content(session, cid)


def test_evidence_content_roundtrip(session):
    content_hash = _sha256("Raw text body of article.")
    cid = _content_id(content_hash)
    _clean_content(session, cid)

    content = EvidenceContent(
        evidence_content_id=cid,
        content_hash=content_hash,
        kind="text",
        text="Raw text body of article.",
        raw_ref_kind="s3",
        raw_ref_id="s3://bucket/key",
        captured_at=NOW,
        v=1,
    )
    session.add(content)
    session.commit()
    session.expire(content)

    found = session.get(EvidenceContent, cid)
    assert found.content_hash == content_hash
    assert found.kind == "text"
    assert found.raw_ref_kind == "s3"
    assert found.raw_ref_id == "s3://bucket/key"

    _clean_content(session, cid)


# ---------------------------------------------------------------------------
# Confidence constraint tests
# ---------------------------------------------------------------------------


def test_confidence_at_zero_accepted(session):
    eid = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/conf0",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="zero",
    )
    _clean_evidence(session, eid)

    ev = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid, "confidence": 0.0})
    session.add(ev)
    session.commit()

    found = session.get(Evidence, eid)
    assert found.confidence == 0.0
    _clean_evidence(session, eid)


def test_confidence_at_one_accepted(session):
    eid = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/conf1",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="one",
    )
    _clean_evidence(session, eid)

    ev = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid, "confidence": 1.0})
    session.add(ev)
    session.commit()

    found = session.get(Evidence, eid)
    assert found.confidence == 1.0
    _clean_evidence(session, eid)


def test_confidence_above_one_rejected(session):
    eid = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/confbad",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="bad",
    )
    _clean_evidence(session, eid)

    ev = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid, "confidence": 1.1})
    session.add(ev)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_confidence_below_zero_rejected(session):
    eid = make_evidence_id(
        source_type="web_page",
        canonical_url="https://example.com/confneg",
        captured_at_iso="2026-03-08T12:00:00+00:00",
        snippet_text="neg",
    )
    _clean_evidence(session, eid)

    ev = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid, "confidence": -0.1})
    session.add(ev)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


# ---------------------------------------------------------------------------
# Replay safety test
# ---------------------------------------------------------------------------


def test_replay_same_evidence_id_is_no_op(session):
    """Re-inserting same evidence_id must not create duplicate logical records."""
    eid = _make_eid()
    _clean_evidence(session, eid)

    ev1 = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid})
    session.add(ev1)
    session.commit()

    # Second insert from a different session must fail at DB level.
    with Session(session.get_bind()) as session2:
        ev2 = Evidence(**{**SAMPLE_EVIDENCE, "evidence_id": eid})
        session2.add(ev2)
        with pytest.raises(IntegrityError):
            session2.commit()
        session2.rollback()

    # Verify only one row exists
    rows = session.query(Evidence).filter(Evidence.evidence_id == eid).all()
    assert len(rows) == 1

    _clean_evidence(session, eid)


# ---------------------------------------------------------------------------
# content_hash uniqueness test
# ---------------------------------------------------------------------------


def test_duplicate_content_hash_rejected(session):
    content_hash = _sha256("Unique content body.")
    cid1 = _content_id(content_hash)
    cid2 = "content:different_id_same_hash"
    _clean_content(session, cid1, cid2)

    c1 = EvidenceContent(
        evidence_content_id=cid1,
        content_hash=content_hash,
        kind="text",
        text="Unique content body.",
        raw_ref_kind=None,
        raw_ref_id=None,
        captured_at=NOW,
        v=1,
    )
    session.add(c1)
    session.commit()

    c2 = EvidenceContent(
        evidence_content_id=cid2,
        content_hash=content_hash,
        kind="text",
        text="Unique content body.",
        raw_ref_kind=None,
        raw_ref_id=None,
        captured_at=NOW,
        v=1,
    )
    session.add(c2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    _clean_content(session, cid1)


# ---------------------------------------------------------------------------
# Schema inspection tests
# ---------------------------------------------------------------------------


def test_evidence_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "evidence" in inspector.get_table_names()


def test_evidence_contents_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "evidence_contents" in inspector.get_table_names()


def test_required_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    ev_indexes = {idx["name"] for idx in inspector.get_indexes("evidence")}
    ec_indexes = {idx["name"] for idx in inspector.get_indexes("evidence_contents")}
    assert "ix_evidence_canonical_url" in ev_indexes
    assert "ix_evidence_captured_at" in ev_indexes
    assert "ix_evidence_content_ref_id" in ev_indexes
    assert "ix_evidence_contents_content_hash" in ec_indexes


def test_confidence_check_constraint_exists(db_engine):
    inspector = inspect(db_engine)
    constraints = inspector.get_check_constraints("evidence")
    names = {c["name"] for c in constraints}
    assert "ck_evidence_confidence_range" in names


# ---------------------------------------------------------------------------
# Contract guard tests
# ---------------------------------------------------------------------------


def test_evidence_coexists_with_all_epic_c_tables(db_engine):
    # structured_events was added in Epic C — evidence must still coexist
    tables = inspect(db_engine).get_table_names()
    assert "evidence" in tables
    assert "structured_events" in tables


def test_no_trace_table(db_engine):
    inspector = inspect(db_engine)
    assert "trace" not in inspector.get_table_names()
    assert "traces" not in inspector.get_table_names()
