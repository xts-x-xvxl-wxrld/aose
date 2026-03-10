"""
Tests for Epic B6: Scorecard persistence.

Requires a live Postgres instance (DATABASE_URL env var).
Tests are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from aose_api.ids import make_scorecard_id
from aose_api.models import Scorecard, validate_reasons


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

NOW = datetime(2026, 3, 8, 14, 0, 0, tzinfo=timezone.utc)
NOW_ISO = "2026-03-08T14:00:00+00:00"

SAMPLE_REASONS = [
    {
        "code": "firmographic_match",
        "text": "Matches EMS segment",
        "evidence_ids": ["evidence:abc123"],
    },
    {
        "code": "hiring_signal",
        "text": "Active hiring in target role",
        "evidence_ids": ["evidence:def456"],
    },
]

SAMPLE_SCORECARD = dict(
    entity_ref_type="account",
    entity_ref_id="account:SI-1234567",
    policy_pack_id="safe_v0_1",
    fit_score=82,
    fit_confidence=0.9,
    fit_reasons_json=SAMPLE_REASONS,
    intent_score=65,
    intent_confidence=0.75,
    intent_reasons_json=[
        {
            "code": "recent_funding",
            "text": "Recent funding round",
            "evidence_ids": ["evidence:def456"],
        }
    ],
    scoring_version="fit_intent_rules_v0_1",
    evidence_snapshot_hash="",
    computed_at=NOW,
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


@pytest.fixture(autouse=True)
def seed_reason_evidence(request):
    if "session" not in request.fixturenames:
        return
    session = request.getfixturevalue("session")
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")


def _make_sid(entity_ref_id: str = "account:SI-1234567") -> str:
    return make_scorecard_id(
        entity_ref_type="account",
        entity_ref_id=entity_ref_id,
        computed_at_iso=NOW_ISO,
    )


def _clean(session: Session, *scorecard_ids: str) -> None:
    for sid in scorecard_ids:
        row = session.get(Scorecard, sid)
        if row:
            session.delete(row)
    session.commit()


def _ensure_evidence(session: Session, *evidence_ids: str) -> None:
    for evidence_id in evidence_ids:
        session.execute(
            text(
                """
            INSERT INTO evidence (
                evidence_id, source_type, canonical_url, captured_at, snippet,
                claim_frame, source_provider, source_ref, observed_at,
                confidence, category, provenance_json, content_ref_id, v
            ) VALUES (
                :evidence_id, 'web_page', 'https://example.com', :ts, 'snippet',
                'claim', 'seed', 'seed-ref', :ts,
                0.9, 'firmographic', '{}'::jsonb, NULL, 1
            ) ON CONFLICT (evidence_id) DO NOTHING
            """
            ),
            {"evidence_id": evidence_id, "ts": NOW},
        )
    session.commit()


# ---------------------------------------------------------------------------
# make_scorecard_id determinism tests (pure, no DB)
# ---------------------------------------------------------------------------


def test_scorecard_id_deterministic():
    sid1 = make_scorecard_id("account", "account:SI-1234567", NOW_ISO)
    sid2 = make_scorecard_id("account", "account:SI-1234567", NOW_ISO)
    assert sid1 == sid2
    assert sid1.startswith("scorecard:")


def test_different_entities_produce_different_ids():
    sid_a = make_scorecard_id("account", "account:SI-1234567", NOW_ISO)
    sid_b = make_scorecard_id("account", "account:SI-9999999", NOW_ISO)
    assert sid_a != sid_b


def test_different_computed_at_produce_different_ids():
    sid_a = make_scorecard_id(
        "account", "account:SI-1234567", "2026-03-08T14:00:00+00:00"
    )
    sid_b = make_scorecard_id(
        "account", "account:SI-1234567", "2026-03-08T15:00:00+00:00"
    )
    assert sid_a != sid_b


# ---------------------------------------------------------------------------
# validate_reasons tests (pure, no DB)
# ---------------------------------------------------------------------------


def test_validate_reasons_accepts_valid():
    assert validate_reasons(
        [{"code": "good_fit", "text": "Good fit", "evidence_ids": ["evidence:abc"]}]
    ) == [{"code": "good_fit", "text": "Good fit", "evidence_ids": ["evidence:abc"]}]


def test_validate_reasons_accepts_empty_list():
    assert validate_reasons([]) == []


def test_validate_reasons_rejects_missing_text():
    with pytest.raises(ValueError, match="text"):
        validate_reasons([{"code": "c", "evidence_ids": ["evidence:abc"]}])


def test_validate_reasons_rejects_missing_code():
    with pytest.raises(ValueError, match="code"):
        validate_reasons([{"text": "x", "evidence_ids": ["evidence:abc"]}])


def test_validate_reasons_rejects_missing_evidence_ids():
    with pytest.raises(ValueError, match="evidence_ids"):
        validate_reasons([{"code": "c", "text": "Some reason"}])


def test_validate_reasons_rejects_non_list_evidence_ids():
    with pytest.raises(ValueError, match="evidence_ids"):
        validate_reasons(
            [{"code": "c", "text": "Some reason", "evidence_ids": "evidence:abc"}]
        )


def test_validate_reasons_rejects_empty_evidence_ids():
    with pytest.raises(ValueError, match="non-empty evidence_ids"):
        validate_reasons([{"code": "c", "text": "Inferred signal", "evidence_ids": []}])


def test_validate_reasons_rejects_non_list_input():
    with pytest.raises(ValueError, match="list"):
        validate_reasons({"text": "not a list"})  # type: ignore[arg-type]


def test_validate_reasons_rejects_non_dict_reason():
    with pytest.raises(ValueError, match="object"):
        validate_reasons(["not a dict"])  # type: ignore[list-item]


# ---------------------------------------------------------------------------
# Schema / model tests
# ---------------------------------------------------------------------------


def test_scorecard_create_and_read(session):
    sid = _make_sid()
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")

    sc = Scorecard(**{**SAMPLE_SCORECARD, "scorecard_id": sid})
    session.add(sc)
    session.commit()
    session.expire(sc)

    found = session.get(Scorecard, sid)
    assert found is not None
    assert found.scorecard_id == sid
    assert found.entity_ref_type == "account"
    assert found.entity_ref_id == "account:SI-1234567"
    assert found.policy_pack_id == "safe_v0_1"
    assert found.v == 1

    _clean(session, sid)


def test_policy_pack_id_persists(session):
    sid = _make_sid()
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")

    sc = Scorecard(
        **{**SAMPLE_SCORECARD, "scorecard_id": sid, "policy_pack_id": "safe_v0_1"}
    )
    session.add(sc)
    session.commit()
    session.expire(sc)

    found = session.get(Scorecard, sid)
    assert found.policy_pack_id == "safe_v0_1"

    _clean(session, sid)


def test_fit_and_intent_stored_separately(session):
    sid = _make_sid()
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")

    sc = Scorecard(**{**SAMPLE_SCORECARD, "scorecard_id": sid})
    session.add(sc)
    session.commit()
    session.expire(sc)

    found = session.get(Scorecard, sid)
    assert found.fit_score == 82
    assert found.fit_confidence == pytest.approx(0.9)
    assert found.intent_score == 65
    assert found.intent_confidence == pytest.approx(0.75)

    _clean(session, sid)


def test_fit_reasons_preserve_text_and_evidence_ids(session):
    sid = _make_sid()
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")

    sc = Scorecard(**{**SAMPLE_SCORECARD, "scorecard_id": sid})
    session.add(sc)
    session.commit()
    session.expire(sc)

    found = session.get(Scorecard, sid)
    reasons = found.fit_reasons_json
    assert len(reasons) == 2
    assert reasons[0]["code"] == "firmographic_match"
    assert reasons[0]["text"] == "Matches EMS segment"
    assert reasons[0]["evidence_ids"] == ["evidence:abc123"]
    assert reasons[1]["code"] == "hiring_signal"
    assert reasons[1]["text"] == "Active hiring in target role"
    assert reasons[1]["evidence_ids"] == ["evidence:def456"]

    _clean(session, sid)


def test_intent_reasons_preserve_text_and_evidence_ids(session):
    sid = _make_sid()
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")

    sc = Scorecard(**{**SAMPLE_SCORECARD, "scorecard_id": sid})
    session.add(sc)
    session.commit()
    session.expire(sc)

    found = session.get(Scorecard, sid)
    reasons = found.intent_reasons_json
    assert len(reasons) == 1
    assert reasons[0]["code"] == "recent_funding"
    assert reasons[0]["text"] == "Recent funding round"
    assert reasons[0]["evidence_ids"] == ["evidence:def456"]
    _clean(session, sid)


def test_scorecard_model_rejects_invalid_fit_reasons_on_insert(session):
    sid = make_scorecard_id("account", "account:bad-fit-reasons", NOW_ISO)
    _clean(session, sid)
    with pytest.raises(ValueError, match="text"):
        Scorecard(
            **{
                **SAMPLE_SCORECARD,
                "scorecard_id": sid,
                "entity_ref_id": "account:bad-fit-reasons",
                "fit_reasons_json": [
                    {"code": "x", "evidence_ids": ["evidence:abc123"]}
                ],
            }
        )
    session.rollback()


def test_scorecard_model_rejects_invalid_intent_reasons_on_insert(session):
    sid = make_scorecard_id("account", "account:bad-intent-reasons", NOW_ISO)
    _clean(session, sid)
    with pytest.raises(ValueError, match="evidence_ids"):
        Scorecard(
            **{
                **SAMPLE_SCORECARD,
                "scorecard_id": sid,
                "entity_ref_id": "account:bad-intent-reasons",
                "intent_reasons_json": [
                    {"code": "x", "text": "x", "evidence_ids": "evidence:def456"}
                ],
            }
        )
    session.rollback()

    with pytest.raises(ValueError, match="non-empty evidence_ids"):
        session.add(
            Scorecard(
                **{
                    **SAMPLE_SCORECARD,
                    "scorecard_id": sid,
                    "entity_ref_id": "account:empty-ev",
                    "fit_reasons_json": [
                        {"code": "inferred", "text": "Inferred", "evidence_ids": []}
                    ],
                    "intent_reasons_json": [
                        {"code": "weak", "text": "Weak signal", "evidence_ids": []}
                    ],
                }
            )
        )
        session.flush()
    session.rollback()


def test_scorecard_model_rejects_unknown_reason_evidence_id_on_insert(session):
    sid = make_scorecard_id("account", "account:missing-ev", NOW_ISO)
    _clean(session, sid)
    sc = Scorecard(
        **{
            **SAMPLE_SCORECARD,
            "scorecard_id": sid,
            "entity_ref_id": "account:missing-ev",
            "fit_reasons_json": [
                {
                    "code": "firmographic_match",
                    "text": "Matches EMS segment",
                    "evidence_ids": ["evidence:missing"],
                }
            ],
        }
    )
    session.add(sc)
    with pytest.raises(ValueError, match="unknown evidence_ids"):
        session.commit()
    session.rollback()


# ---------------------------------------------------------------------------
# Constraint tests
# ---------------------------------------------------------------------------


def test_fit_confidence_above_one_rejected(session):
    sid = make_scorecard_id("account", "account:bad-fc", NOW_ISO)
    _clean(session, sid)
    sc = Scorecard(
        **{
            **SAMPLE_SCORECARD,
            "scorecard_id": sid,
            "entity_ref_id": "account:bad-fc",
            "fit_confidence": 1.1,
        }
    )
    session.add(sc)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_fit_confidence_below_zero_rejected(session):
    sid = make_scorecard_id("account", "account:bad-fc2", NOW_ISO)
    _clean(session, sid)
    sc = Scorecard(
        **{
            **SAMPLE_SCORECARD,
            "scorecard_id": sid,
            "entity_ref_id": "account:bad-fc2",
            "fit_confidence": -0.1,
        }
    )
    session.add(sc)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_intent_confidence_above_one_rejected(session):
    sid = make_scorecard_id("account", "account:bad-ic", NOW_ISO)
    _clean(session, sid)
    sc = Scorecard(
        **{
            **SAMPLE_SCORECARD,
            "scorecard_id": sid,
            "entity_ref_id": "account:bad-ic",
            "intent_confidence": 1.5,
        }
    )
    session.add(sc)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_fit_score_above_hundred_rejected(session):
    sid = make_scorecard_id("account", "account:bad-fs", NOW_ISO)
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")
    sc = Scorecard(
        **{
            **SAMPLE_SCORECARD,
            "scorecard_id": sid,
            "entity_ref_id": "account:bad-fs",
            "fit_score": 120,
        }
    )
    session.add(sc)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_intent_score_below_zero_rejected(session):
    sid = make_scorecard_id("account", "account:bad-is", NOW_ISO)
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")
    sc = Scorecard(
        **{
            **SAMPLE_SCORECARD,
            "scorecard_id": sid,
            "entity_ref_id": "account:bad-is",
            "intent_score": -1,
        }
    )
    session.add(sc)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_boundary_values_accepted(session):
    sid = make_scorecard_id("account", "account:boundary", NOW_ISO)
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")
    sc = Scorecard(
        **{
            **SAMPLE_SCORECARD,
            "scorecard_id": sid,
            "entity_ref_id": "account:boundary",
            "fit_score": 0,
            "fit_confidence": 1.0,
            "intent_score": 100,
            "intent_confidence": 0.0,
        }
    )
    session.add(sc)
    session.commit()
    found = session.get(Scorecard, sid)
    assert found.fit_score == 0
    assert found.fit_confidence == 1.0
    _clean(session, sid)


# ---------------------------------------------------------------------------
# Replay safety test
# ---------------------------------------------------------------------------


def test_replay_same_scorecard_id_rejected(session):
    """Same scoring snapshot (same ID) must not create duplicate logical records."""
    sid = _make_sid()
    _clean(session, sid)
    _ensure_evidence(session, "evidence:abc123", "evidence:def456")

    sc1 = Scorecard(**{**SAMPLE_SCORECARD, "scorecard_id": sid})
    session.add(sc1)
    session.commit()

    # Use a fresh session to properly hit the DB-level PK constraint
    with Session(session.bind) as s2:
        sc2 = Scorecard(**{**SAMPLE_SCORECARD, "scorecard_id": sid})
        s2.add(sc2)
        with pytest.raises(IntegrityError):
            s2.commit()

    rows = session.query(Scorecard).filter(Scorecard.scorecard_id == sid).all()
    assert len(rows) == 1

    _clean(session, sid)


# ---------------------------------------------------------------------------
# Schema inspection tests
# ---------------------------------------------------------------------------


def test_scorecards_table_exists(db_engine):
    inspector = inspect(db_engine)
    assert "scorecards" in inspector.get_table_names()


def test_required_indexes_exist(db_engine):
    inspector = inspect(db_engine)
    index_names = {idx["name"] for idx in inspector.get_indexes("scorecards")}
    assert "ix_scorecards_entity_ref" in index_names
    assert "ix_scorecards_computed_at" in index_names


def test_check_constraints_exist(db_engine):
    inspector = inspect(db_engine)
    constraints = {c["name"] for c in inspector.get_check_constraints("scorecards")}
    assert "ck_scorecards_fit_score_range" in constraints
    assert "ck_scorecards_fit_confidence_range" in constraints
    assert "ck_scorecards_intent_score_range" in constraints
    assert "ck_scorecards_intent_confidence_range" in constraints


# ---------------------------------------------------------------------------
# Contract guard tests
# ---------------------------------------------------------------------------


def test_no_draft_table(db_engine):
    inspector = inspect(db_engine)
    assert "drafts" not in inspector.get_table_names()
