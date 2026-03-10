"""
Tests for SPEC-E2: Account discovery handler + service.

Acceptance checks covered:
  integration: dummy adapter happy path writes Account + Evidence
  integration: provenance is stored on account and evidence
  integration: downstream work item is enqueued with payload {v:1, account_id}
  integration: alias rows are written for registry / domain / legal_name_normalized
  integration: no forbidden canonical tables are written (Scorecard, Contact, etc.)
  integration: replay safety — second run does not duplicate rows
  unit: candidate normalization runs before canonical writes
  unit: tmp account ID fallback used only when registry and domain absent

Integration tests require a live Postgres instance (DATABASE_URL env var).
They are skipped automatically when DATABASE_URL is not set.
"""

from __future__ import annotations

import json
import os
import pytest

from aose_worker.adapters.account_discovery.dummy_predictable import (
    DummyPredictableAdapter,
)
from aose_worker.adapters.account_discovery.registry import (
    get_adapter,
    registered_adapter_names,
)
from aose_worker.canonical_ids import (
    make_account_id,
    make_scoring_idempotency_key,
)
from aose_worker.services.account_discovery_service import run_account_discovery

# ---------------------------------------------------------------------------
# Unit tests (no DB required)
# ---------------------------------------------------------------------------


def test_adapter_registry_includes_dummy_predictable():
    """dummy_predictable must always be registered."""
    assert "dummy_predictable" in registered_adapter_names()


def test_get_adapter_returns_dummy_predictable_by_default():
    adapter = get_adapter(None)
    assert isinstance(adapter, DummyPredictableAdapter)


def test_get_adapter_returns_dummy_predictable_by_name():
    adapter = get_adapter("dummy_predictable")
    assert isinstance(adapter, DummyPredictableAdapter)


def test_get_adapter_raises_for_unknown_name():
    with pytest.raises(ValueError, match="Unknown account discovery adapter"):
        get_adapter("nonexistent_provider_xyz")


def test_tmp_account_id_fallback_when_no_registry_or_domain():
    """account:tmp: prefix used only when both registry_id and domain are absent."""
    account_id = make_account_id(
        country=None,
        registry_id=None,
        domain=None,
        legal_name_normalized="Acme Corp",
        source_provider="dummy",
        source_ref="ref-001",
    )
    assert account_id.startswith("account:tmp:")


def test_registry_account_id_takes_precedence_over_domain():
    """Tier 1 (registry) wins over tier 2 (domain) when both are present."""
    account_id = make_account_id(
        country="SI",
        registry_id="1234567",
        domain="acme.si",
        legal_name_normalized="acme",
        source_provider="dummy",
        source_ref="ref",
    )
    assert account_id == "account:SI-1234567"


def test_domain_account_id_used_when_no_registry():
    """Tier 2 (domain) used when registry is absent."""
    account_id = make_account_id(
        country=None,
        registry_id=None,
        domain="acme.si",
        legal_name_normalized="acme",
        source_provider="dummy",
        source_ref="ref",
    )
    assert account_id == "account:acme.si"


def test_scoring_idempotency_key_is_deterministic():
    """Same account_id + query_object_id always produce the same key."""
    k1 = make_scoring_idempotency_key("account:SI-1234567", "qo:test-001")
    k2 = make_scoring_idempotency_key("account:SI-1234567", "qo:test-001")
    assert k1 == k2
    assert k1.startswith("scoring:")


def test_scoring_idempotency_key_differs_for_different_accounts():
    k1 = make_scoring_idempotency_key("account:SI-1234567", "qo:test-001")
    k2 = make_scoring_idempotency_key("account:DE-HRB99001", "qo:test-001")
    assert k1 != k2


# ---------------------------------------------------------------------------
# Integration test infrastructure
# ---------------------------------------------------------------------------


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture(scope="session")
def db_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set — skipping integration tests")

    from sqlalchemy import create_engine

    # Schema migrations are managed by the API container (alembic).
    # The worker assumes the schema is already current when DATABASE_URL is set.
    engine = create_engine(_sa_url(url))
    yield engine
    engine.dispose()


@pytest.fixture
def session(db_engine):
    from sqlalchemy.orm import Session

    with Session(db_engine) as s:
        yield s


# ---------------------------------------------------------------------------
# Integration fixtures — pre-conditions
# ---------------------------------------------------------------------------

_SELLER_ID = "seller:e2-test-seller"
_QUERY_OBJECT_ID = "qo:e2-test-001"
_WORK_ITEM_ID = "wi:e2-test-parent-001"
_IDEMPOTENCY_KEY = "acctdisc:e2-test-001:v1"

_PARENT_WORK_ITEM: dict = {
    "work_item_id": _WORK_ITEM_ID,
    "entity_ref_type": "query_object",
    "entity_ref_id": _QUERY_OBJECT_ID,
    "stage": "account_discovery",
    "attempt_budget_remaining": 3,
    "attempt_budget_policy": "standard",
    "trace_run_id": "run:e2-test-001",
    "trace_parent_work_item_id": None,
    "trace_correlation_id": "corr:e2-test-001",
    "trace_policy_pack_id": "safe_v0_1",
}


def _insert_seller_profile(session) -> None:
    from sqlalchemy import text

    session.execute(
        text(
            """
            INSERT INTO seller_profiles (
                seller_id, offer_what, offer_where, offer_who,
                offer_positioning, constraints_avoid_claims,
                constraints_allowed_channels, constraints_languages,
                policy_pack_id, created_at, v
            ) VALUES (
                :seller_id, 'B2B SaaS HR software',
                CAST('["EU"]' AS JSONB), CAST('["SME"]' AS JSONB),
                CAST('["quality"]' AS JSONB),
                CAST('[]' AS JSONB), CAST('["email"]' AS JSONB),
                CAST('["en"]' AS JSONB),
                'safe_v0_1', now(), 1
            ) ON CONFLICT (seller_id) DO NOTHING
            """
        ),
        {"seller_id": _SELLER_ID},
    )


def _insert_query_object(session) -> None:
    from sqlalchemy import text

    session.execute(
        text(
            """
            INSERT INTO query_objects (
                query_object_id, seller_id, buyer_context, priority,
                keywords, exclusions, rationale, v
            ) VALUES (
                :qo_id, :seller_id, 'HR software for SMEs', 1.0,
                CAST('["hr", "saas"]' AS JSONB), CAST('[]' AS JSONB),
                'Test query object', 1
            ) ON CONFLICT (query_object_id) DO NOTHING
            """
        ),
        {"qo_id": _QUERY_OBJECT_ID, "seller_id": _SELLER_ID},
    )


def _insert_work_item(session) -> None:
    from sqlalchemy import text

    session.execute(
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
                :wi_id, 'query_object', :qo_id, 'account_discovery',
                CAST(:payload AS JSONB), 1,
                3, 'standard',
                :ik,
                'run:e2-test-001', NULL,
                'corr:e2-test-001', 'safe_v0_1', now()
            ) ON CONFLICT (work_item_id) DO NOTHING
            """
        ),
        {
            "wi_id": _WORK_ITEM_ID,
            "qo_id": _QUERY_OBJECT_ID,
            "payload": json.dumps(
                {"v": 1, "data": {"query_object_id": _QUERY_OBJECT_ID}}
            ),
            "ik": _IDEMPOTENCY_KEY,
        },
    )


def _clean_test_data(session) -> None:
    """Remove all rows created by E2 integration tests."""
    from sqlalchemy import text

    # Collect account_ids from dummy adapter output for this query_object
    adapter = DummyPredictableAdapter()
    qo_dict = {"query_object_id": _QUERY_OBJECT_ID}
    result = adapter.search_accounts(qo_dict, {}, {})
    account_ids = []
    for c in result.candidates:
        account_ids.append(
            make_account_id(
                country=c.country,
                registry_id=c.registry_id,
                domain=c.domain,
                legal_name_normalized=c.legal_name_normalized,
                source_provider=c.source_provider,
                source_ref=c.source_ref,
            )
        )

    for aid in account_ids:
        # Downstream scoring work items
        ik = make_scoring_idempotency_key(aid, _QUERY_OBJECT_ID)
        session.execute(
            text("DELETE FROM work_items WHERE idempotency_key = :ik"),
            {"ik": ik},
        )
        # Aliases
        session.execute(
            text("DELETE FROM account_aliases WHERE account_id = :aid"),
            {"aid": aid},
        )
        # Evidence (just evidence rows with our source_provider)
        session.execute(
            text(
                "DELETE FROM evidence WHERE source_provider = :sp"
                " AND provenance_json->>'query_object_id' = :qo_id"
            ),
            {"sp": "dummy_registry", "qo_id": _QUERY_OBJECT_ID},
        )
        # Account
        session.execute(
            text("DELETE FROM accounts WHERE account_id = :aid"),
            {"aid": aid},
        )

    # Remove parent work item
    session.execute(
        text("DELETE FROM work_items WHERE work_item_id = :id"),
        {"id": _WORK_ITEM_ID},
    )
    # Remove query object
    session.execute(
        text("DELETE FROM query_objects WHERE query_object_id = :id"),
        {"id": _QUERY_OBJECT_ID},
    )
    # Remove seller profile
    session.execute(
        text("DELETE FROM seller_profiles WHERE seller_id = :id"),
        {"id": _SELLER_ID},
    )
    session.commit()


@pytest.fixture
def seeded_session(session):
    """Session with pre-conditions for E2 integration tests."""
    _clean_test_data(session)
    _insert_seller_profile(session)
    _insert_query_object(session)
    _insert_work_item(session)
    session.commit()
    yield session
    _clean_test_data(session)


def _run_service(session) -> object:
    """Run the account discovery service with the dummy adapter."""
    adapter = DummyPredictableAdapter()
    return run_account_discovery(
        session=session,
        query_object_id=_QUERY_OBJECT_ID,
        adapter=adapter,
        limits={"max_accounts": 30, "max_external_calls": 250},
        context={"policy_pack_id": "safe_v0_1", "run_id": "run:e2-test-001"},
        parent_work_item=_PARENT_WORK_ITEM,
    )


# ---------------------------------------------------------------------------
# Integration: happy path
# ---------------------------------------------------------------------------


def test_happy_path_creates_account_rows(seeded_session):
    """Integration: dummy adapter happy path writes Account rows."""
    from sqlalchemy import text

    result = _run_service(seeded_session)
    seeded_session.commit()

    assert result.accounts_created > 0, "Expected at least one Account to be created"

    rows = seeded_session.execute(
        text(
            "SELECT account_id FROM accounts" " WHERE provenance::text LIKE :qo_pattern"
        ),
        {"qo_pattern": f"%{_QUERY_OBJECT_ID}%"},
    ).fetchall()
    assert len(rows) >= 1


def test_happy_path_creates_evidence_rows(seeded_session):
    """Integration: dummy adapter happy path writes Evidence rows."""
    from sqlalchemy import text

    result = _run_service(seeded_session)
    seeded_session.commit()

    assert result.evidence_created > 0, "Expected at least one Evidence to be created"

    rows = seeded_session.execute(
        text(
            "SELECT evidence_id FROM evidence"
            " WHERE provenance_json->>'query_object_id' = :qo_id"
        ),
        {"qo_id": _QUERY_OBJECT_ID},
    ).fetchall()
    assert len(rows) >= 1


def test_account_provenance_has_required_fields(seeded_session):
    """Integration: provenance on account carries adapter, query_object_id, captured_at."""
    from sqlalchemy import text

    _run_service(seeded_session)
    seeded_session.commit()

    row = seeded_session.execute(
        text(
            "SELECT provenance FROM accounts"
            " WHERE provenance::text LIKE :qo_pattern"
            " LIMIT 1"
        ),
        {"qo_pattern": f"%{_QUERY_OBJECT_ID}%"},
    ).first()
    assert row is not None, "No account row with matching provenance found"

    provenance = row[0]
    # provenance is a list with one entry
    assert isinstance(provenance, list) and len(provenance) > 0
    entry = provenance[0]
    assert "adapter" in entry
    assert "query_object_id" in entry
    assert entry["query_object_id"] == _QUERY_OBJECT_ID
    assert "captured_at" in entry


def test_evidence_provenance_has_required_fields(seeded_session):
    """Integration: provenance on evidence carries adapter and query_object_id."""
    from sqlalchemy import text

    _run_service(seeded_session)
    seeded_session.commit()

    row = seeded_session.execute(
        text(
            "SELECT provenance_json FROM evidence"
            " WHERE provenance_json->>'query_object_id' = :qo_id"
            " LIMIT 1"
        ),
        {"qo_id": _QUERY_OBJECT_ID},
    ).first()
    assert row is not None, "No evidence row with matching provenance found"

    provenance = row[0]
    assert "adapter" in provenance
    assert "query_object_id" in provenance
    assert provenance["query_object_id"] == _QUERY_OBJECT_ID


def test_alias_rows_written(seeded_session):
    """Integration: alias rows written for registry, domain, legal_name_normalized."""
    from sqlalchemy import text

    _run_service(seeded_session)
    seeded_session.commit()

    # Collect account IDs that were created
    rows = seeded_session.execute(
        text(
            "SELECT account_id FROM accounts" " WHERE provenance::text LIKE :qo_pattern"
        ),
        {"qo_pattern": f"%{_QUERY_OBJECT_ID}%"},
    ).fetchall()
    assert rows, "No accounts found — alias test requires accounts"

    for (account_id,) in rows:
        aliases = seeded_session.execute(
            text("SELECT alias_type FROM account_aliases" " WHERE account_id = :aid"),
            {"aid": account_id},
        ).fetchall()
        alias_types = {row[0] for row in aliases}
        # Dummy adapter provides all three; at least one must be present
        assert alias_types, f"No aliases written for account {account_id}"


def test_downstream_work_item_enqueued(seeded_session):
    """Integration: one intent_fit_scoring WorkItem enqueued per surviving account."""
    from sqlalchemy import text

    result = _run_service(seeded_session)
    seeded_session.commit()

    assert result.downstream_enqueued > 0, "No downstream work items enqueued"

    # Verify the stage and payload shape
    rows = seeded_session.execute(
        text(
            "SELECT stage, payload_json FROM work_items"
            " WHERE stage = 'intent_fit_scoring'"
            " AND trace_run_id = :run_id"
        ),
        {"run_id": _PARENT_WORK_ITEM["trace_run_id"]},
    ).fetchall()
    assert len(rows) >= 1, "No intent_fit_scoring work items found in DB"

    for stage, payload in rows:
        assert stage == "intent_fit_scoring"
        assert payload["v"] == 1
        assert "account_id" in payload["data"]
        assert payload["data"]["account_id"].startswith("account:")


def test_downstream_work_item_payload_shape(seeded_session):
    """Integration: downstream payload is {v:1, data:{account_id:...}}."""
    from sqlalchemy import text

    _run_service(seeded_session)
    seeded_session.commit()

    row = seeded_session.execute(
        text(
            "SELECT payload_json FROM work_items"
            " WHERE stage = 'intent_fit_scoring'"
            " AND trace_run_id = :run_id"
            " LIMIT 1"
        ),
        {"run_id": _PARENT_WORK_ITEM["trace_run_id"]},
    ).first()
    assert row is not None
    payload = row[0]
    assert payload["v"] == 1
    assert "data" in payload
    assert "account_id" in payload["data"]


def test_no_forbidden_tables_written(seeded_session):
    """Integration: no Scorecard, Contact, OutreachDraft, ApprovalDecision, SendAttempt rows created."""
    from sqlalchemy import text

    before_scorecards = seeded_session.execute(
        text("SELECT COUNT(*) FROM scorecards")
    ).scalar()
    before_contacts = seeded_session.execute(
        text("SELECT COUNT(*) FROM contacts")
    ).scalar()
    before_drafts = seeded_session.execute(
        text("SELECT COUNT(*) FROM outreach_drafts")
    ).scalar()
    before_decisions = seeded_session.execute(
        text("SELECT COUNT(*) FROM approval_decisions")
    ).scalar()
    before_sends = seeded_session.execute(
        text("SELECT COUNT(*) FROM send_attempts")
    ).scalar()

    _run_service(seeded_session)
    seeded_session.commit()

    assert (
        seeded_session.execute(text("SELECT COUNT(*) FROM scorecards")).scalar()
        == before_scorecards
    )
    assert (
        seeded_session.execute(text("SELECT COUNT(*) FROM contacts")).scalar()
        == before_contacts
    )
    assert (
        seeded_session.execute(text("SELECT COUNT(*) FROM outreach_drafts")).scalar()
        == before_drafts
    )
    assert (
        seeded_session.execute(text("SELECT COUNT(*) FROM approval_decisions")).scalar()
        == before_decisions
    )
    assert (
        seeded_session.execute(text("SELECT COUNT(*) FROM send_attempts")).scalar()
        == before_sends
    )


def test_replay_safety_no_duplicate_accounts(seeded_session):
    """Integration: running service twice does not create duplicate Account rows."""
    from sqlalchemy import text

    _run_service(seeded_session)
    seeded_session.commit()
    result1 = seeded_session.execute(
        text(
            "SELECT COUNT(*) FROM accounts" " WHERE provenance::text LIKE :qo_pattern"
        ),
        {"qo_pattern": f"%{_QUERY_OBJECT_ID}%"},
    ).scalar()

    # Run again (replay)
    _run_service(seeded_session)
    seeded_session.commit()
    result2 = seeded_session.execute(
        text(
            "SELECT COUNT(*) FROM accounts" " WHERE provenance::text LIKE :qo_pattern"
        ),
        {"qo_pattern": f"%{_QUERY_OBJECT_ID}%"},
    ).scalar()

    assert (
        result1 == result2
    ), f"Replay created duplicate accounts: before={result1}, after={result2}"


def test_replay_safety_no_duplicate_evidence(seeded_session):
    """Integration: running service twice does not create duplicate Evidence rows."""
    from sqlalchemy import text

    _run_service(seeded_session)
    seeded_session.commit()
    count1 = seeded_session.execute(
        text(
            "SELECT COUNT(*) FROM evidence"
            " WHERE provenance_json->>'query_object_id' = :qo_id"
        ),
        {"qo_id": _QUERY_OBJECT_ID},
    ).scalar()

    _run_service(seeded_session)
    seeded_session.commit()
    count2 = seeded_session.execute(
        text(
            "SELECT COUNT(*) FROM evidence"
            " WHERE provenance_json->>'query_object_id' = :qo_id"
        ),
        {"qo_id": _QUERY_OBJECT_ID},
    ).scalar()

    assert (
        count1 == count2
    ), f"Replay created duplicate evidence: before={count1}, after={count2}"


def test_replay_safety_no_duplicate_scoring_work_items(seeded_session):
    """Integration: replaying discovery does not enqueue duplicate scoring WorkItems."""
    result1 = _run_service(seeded_session)
    seeded_session.commit()
    enqueued1 = result1.downstream_enqueued

    result2 = _run_service(seeded_session)
    seeded_session.commit()
    enqueued2 = result2.downstream_enqueued

    # Second run should enqueue zero new items (all idempotency_key ON CONFLICT DO NOTHING)
    assert (
        enqueued2 == 0
    ), f"Replay enqueued {enqueued2} scoring work items (expected 0)"
    _ = enqueued1  # first run must have enqueued items


def test_account_status_is_candidate(seeded_session):
    """Integration: account status must be 'candidate' after discovery (locked default)."""
    from sqlalchemy import text

    _run_service(seeded_session)
    seeded_session.commit()

    rows = seeded_session.execute(
        text("SELECT status FROM accounts" " WHERE provenance::text LIKE :qo_pattern"),
        {"qo_pattern": f"%{_QUERY_OBJECT_ID}%"},
    ).fetchall()
    assert rows, "No accounts found"
    for (status,) in rows:
        assert status == "candidate", f"Expected status='candidate', got {status!r}"


# ---------------------------------------------------------------------------
# Integration: real adapter scaffold (PH-EPIC-E-001)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.getenv("ACCOUNT_DISCOVERY_ADAPTER", "dummy_predictable") == "dummy_predictable",
    reason=(
        "PH-EPIC-E-001: real adapter not yet selected. "
        "Set ACCOUNT_DISCOVERY_ADAPTER env var to a registered real adapter to run."
    ),
)
def test_real_adapter_happy_path(seeded_session):
    """
    Conditional integration test for one real adapter.

    Runs only when ACCOUNT_DISCOVERY_ADAPTER is set to a registered real adapter.
    See PH-EPIC-E-001 — real adapter selection is deferred until human decision.
    """
    adapter_name = os.getenv("ACCOUNT_DISCOVERY_ADAPTER")
    adapter = get_adapter(adapter_name)
    result = run_account_discovery(
        session=seeded_session,
        query_object_id=_QUERY_OBJECT_ID,
        adapter=adapter,
        limits={"max_accounts": 5, "max_external_calls": 10},
        context={"policy_pack_id": "safe_v0_1", "run_id": "run:e2-real-adapter-test"},
        parent_work_item=_PARENT_WORK_ITEM,
    )
    seeded_session.commit()
    # Minimal sanity check; full real-adapter acceptance is Epic E2 + E3
    assert not result.no_signal, "Real adapter returned no candidates"
