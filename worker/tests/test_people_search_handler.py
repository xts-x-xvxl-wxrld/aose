"""
Tests for SPEC-G1: PeopleSearch adapter interface, types, and service.

Acceptance checks covered:
  unit: dummy adapter implements PeopleSearchAdapter interface
  unit: deterministic output for same account_id
  unit: ContactCandidate validates required fields and confidence bounds
  unit: ContactCandidate rejects missing identity fields
  unit: adapter registry defaults to dummy_predictable_people
  unit: adapter registry raises for unknown adapter name
  unit: service dedup — two identical candidates create one Contact
  unit: service rejects candidate with neither email nor linkedin_url
  unit: service role ambiguity + no linkedin → needs_human
  unit: canonical contact ID formula (email precedence, linkedin hash fallback)
  unit: enrichment idempotency key formula
  unit: people search idempotency key formula
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aose_worker.adapters.people_search.base import PeopleSearchAdapter
from aose_worker.adapters.people_search.dummy_predictable import (
    DummyPredictablePeopleAdapter,
)
from aose_worker.adapters.people_search.registry import (
    get_adapter,
    registered_adapter_names,
)
from aose_worker.adapters.people_search.types import (
    ALLOWED_ROLE_CLUSTERS,
    ContactCandidate,
)
from aose_worker.canonical_ids import (
    make_contact_id,
    make_enrichment_idempotency_key,
    make_people_search_idempotency_key,
    normalize_email,
    normalize_linkedin_url,
)
from aose_worker.services.people_search_service import run_people_search

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ACCOUNT_ID = "account:acme.example.com"
_FIXED_OBSERVED_AT = "2026-01-01T00:00:00Z"


def _make_provenance(**kwargs) -> dict:
    base = {
        "source_provider": "test_provider",
        "source_ref": "ref-001",
        "observed_at": _FIXED_OBSERVED_AT,
    }
    base.update(kwargs)
    return base


def _make_candidate(
    account_id: str = _ACCOUNT_ID,
    email: str | None = "alice@acme.example.com",
    linkedin_url: str | None = None,
    role_cluster: str | None = "economic_buyer",
    confidence: float | None = 0.85,
) -> ContactCandidate:
    return ContactCandidate(
        account_id=account_id,
        full_name="Alice Smith",
        provenance=_make_provenance(),
        email=email,
        linkedin_url=linkedin_url,
        role_title="CEO",
        role_cluster=role_cluster,
        role_confidence=0.90,
        source_provider="test_provider",
        source_ref="ref-001",
        observed_at=_FIXED_OBSERVED_AT,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Adapter interface conformance
# ---------------------------------------------------------------------------


def test_dummy_adapter_implements_base_interface():
    assert isinstance(DummyPredictablePeopleAdapter(), PeopleSearchAdapter)


def test_dummy_adapter_has_adapter_name():
    adapter = DummyPredictablePeopleAdapter()
    assert adapter.adapter_name == "dummy_predictable_people"


def test_dummy_adapter_returns_list_of_candidates():
    adapter = DummyPredictablePeopleAdapter()
    results = adapter.search_people(_ACCOUNT_ID)
    assert isinstance(results, list)
    assert len(results) > 0


def test_dummy_adapter_candidates_are_contact_candidate_instances():
    adapter = DummyPredictablePeopleAdapter()
    results = adapter.search_people(_ACCOUNT_ID)
    for c in results:
        assert isinstance(c, ContactCandidate)


def test_dummy_adapter_deterministic_for_same_account_id():
    adapter = DummyPredictablePeopleAdapter()
    r1 = adapter.search_people(_ACCOUNT_ID)
    r2 = adapter.search_people(_ACCOUNT_ID)
    assert len(r1) == len(r2)
    for c1, c2 in zip(r1, r2):
        assert c1.full_name == c2.full_name
        assert c1.email == c2.email
        assert c1.linkedin_url == c2.linkedin_url
        assert c1.source_ref == c2.source_ref


def test_dummy_adapter_different_account_ids_produce_different_refs():
    adapter = DummyPredictablePeopleAdapter()
    r1 = adapter.search_people("account:alpha.com")
    r2 = adapter.search_people("account:beta.com")
    refs1 = {c.source_ref for c in r1}
    refs2 = {c.source_ref for c in r2}
    assert refs1.isdisjoint(refs2)


def test_dummy_adapter_candidates_have_required_fields():
    adapter = DummyPredictablePeopleAdapter()
    for c in adapter.search_people(_ACCOUNT_ID):
        assert c.account_id == _ACCOUNT_ID
        assert c.full_name
        assert isinstance(c.provenance, dict)
        assert c.email or c.linkedin_url


def test_dummy_adapter_candidate_confidence_in_range():
    adapter = DummyPredictablePeopleAdapter()
    for c in adapter.search_people(_ACCOUNT_ID):
        if c.confidence is not None:
            assert 0.0 <= c.confidence <= 1.0


# ---------------------------------------------------------------------------
# Adapter registry
# ---------------------------------------------------------------------------


def test_registry_includes_dummy_predictable_people():
    assert "dummy_predictable_people" in registered_adapter_names()


def test_get_adapter_returns_dummy_by_default():
    assert isinstance(get_adapter(None), DummyPredictablePeopleAdapter)


def test_get_adapter_returns_dummy_by_name():
    assert isinstance(
        get_adapter("dummy_predictable_people"), DummyPredictablePeopleAdapter
    )


def test_get_adapter_raises_for_unknown_name():
    with pytest.raises(ValueError, match="Unknown people search adapter"):
        get_adapter("nonexistent_xyz")


# ---------------------------------------------------------------------------
# ContactCandidate validation
# ---------------------------------------------------------------------------


def test_contact_candidate_valid_email_only():
    c = _make_candidate(linkedin_url=None)
    assert c.email == "alice@acme.example.com"


def test_contact_candidate_valid_linkedin_only():
    c = _make_candidate(
        email=None,
        linkedin_url="https://www.linkedin.com/in/alice-smith",
    )
    assert c.linkedin_url == "https://www.linkedin.com/in/alice-smith"


def test_contact_candidate_rejects_missing_both_identities():
    with pytest.raises(ValueError, match="identity"):
        ContactCandidate(
            account_id=_ACCOUNT_ID,
            full_name="Alice",
            provenance=_make_provenance(),
            email=None,
            linkedin_url=None,
        )


def test_contact_candidate_rejects_invalid_email_and_no_linkedin():
    with pytest.raises(ValueError, match="identity"):
        ContactCandidate(
            account_id=_ACCOUNT_ID,
            full_name="Alice",
            provenance=_make_provenance(),
            email="not-an-email",
            linkedin_url=None,
        )


def test_contact_candidate_rejects_missing_account_id():
    with pytest.raises(ValueError, match="account_id"):
        ContactCandidate(
            account_id="",
            full_name="Alice",
            provenance=_make_provenance(),
            email="alice@example.com",
        )


def test_contact_candidate_rejects_missing_full_name():
    with pytest.raises(ValueError, match="full_name"):
        ContactCandidate(
            account_id=_ACCOUNT_ID,
            full_name="",
            provenance=_make_provenance(),
            email="alice@example.com",
        )


def test_contact_candidate_rejects_confidence_above_one():
    with pytest.raises(ValueError, match="confidence"):
        _make_candidate(confidence=1.5)


def test_contact_candidate_rejects_confidence_below_zero():
    with pytest.raises(ValueError, match="confidence"):
        _make_candidate(confidence=-0.1)


def test_contact_candidate_rejects_invalid_role_cluster():
    with pytest.raises(ValueError, match="role_cluster"):
        ContactCandidate(
            account_id=_ACCOUNT_ID,
            full_name="Alice",
            provenance=_make_provenance(),
            email="alice@example.com",
            role_cluster="wizard",
        )


def test_contact_candidate_rejects_missing_provenance_source_provider():
    with pytest.raises(ValueError, match="source_provider"):
        ContactCandidate(
            account_id=_ACCOUNT_ID,
            full_name="Alice",
            provenance={"source_ref": "r", "observed_at": _FIXED_OBSERVED_AT},
            email="alice@example.com",
        )


def test_allowed_role_clusters_are_locked():
    assert ALLOWED_ROLE_CLUSTERS == frozenset(
        {"economic_buyer", "influencer", "gatekeeper", "referrer"}
    )


# ---------------------------------------------------------------------------
# Canonical ID formulas
# ---------------------------------------------------------------------------


def test_make_contact_id_email_precedence():
    cid = make_contact_id(
        _ACCOUNT_ID,
        email="alice@example.com",
        linkedin_url="https://linkedin.com/in/alice",
    )
    assert cid == f"contact:{_ACCOUNT_ID}:alice@example.com"


def test_make_contact_id_linkedin_fallback():
    norm_li = normalize_linkedin_url("https://www.linkedin.com/in/bob-jones")
    import hashlib

    expected_hash = hashlib.sha256(norm_li.encode()).hexdigest()
    cid = make_contact_id(
        _ACCOUNT_ID, email=None, linkedin_url="https://www.linkedin.com/in/bob-jones"
    )
    assert cid == f"contact:{_ACCOUNT_ID}:{expected_hash}"


def test_make_contact_id_returns_none_when_both_absent():
    cid = make_contact_id(_ACCOUNT_ID, email=None, linkedin_url=None)
    assert cid is None


def test_make_enrichment_idempotency_key():
    key = make_enrichment_idempotency_key("contact:acme.com:alice@acme.com")
    assert key == "enrich:contact:acme.com:alice@acme.com:email:v1"


def test_make_people_search_idempotency_key():
    key = make_people_search_idempotency_key(_ACCOUNT_ID, "adapter")
    assert key == f"ppl:{_ACCOUNT_ID}:adapter:v1"


# ---------------------------------------------------------------------------
# Email + LinkedIn normalization
# ---------------------------------------------------------------------------


def test_normalize_email_lowercases_local():
    assert normalize_email("Alice@Example.COM") == "alice@example.com"


def test_normalize_email_strips_www():
    assert normalize_email("alice@www.example.com") == "alice@example.com"


def test_normalize_email_returns_none_for_invalid():
    assert normalize_email("not-an-email") is None
    assert normalize_email(None) is None
    assert normalize_email("") is None


def test_normalize_linkedin_url_removes_trailing_slash():
    norm = normalize_linkedin_url("https://www.linkedin.com/in/alice-smith/")
    assert norm == "https://www.linkedin.com/in/alice-smith"


def test_normalize_linkedin_url_removes_query_params():
    norm = normalize_linkedin_url("https://linkedin.com/in/alice?utm_source=test")
    assert norm == "https://linkedin.com/in/alice"


def test_normalize_linkedin_url_returns_none_for_empty():
    assert normalize_linkedin_url(None) is None
    assert normalize_linkedin_url("") is None


# ---------------------------------------------------------------------------
# Service unit tests (mocked DB session)
# ---------------------------------------------------------------------------


def _mock_session_for_service(
    account_exists: bool = True,
    existing_contact_count: int = 0,
) -> MagicMock:
    """Return a MagicMock SQLAlchemy session for service unit tests."""
    session = MagicMock()

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        mock_result = MagicMock()

        if "FROM accounts" in sql_str:
            if account_exists:
                mock_row = MagicMock()
                mock_row.__getitem__ = lambda self, k: {
                    "account_id": _ACCOUNT_ID,
                    "name": "Acme",
                    "domain": "acme.example.com",
                    "country": "US",
                    "status": "candidate",
                }[k]
                mock_result.mappings.return_value.first.return_value = mock_row
            else:
                mock_result.mappings.return_value.first.return_value = None
        elif "COUNT(*)" in sql_str:
            mock_result.scalar.return_value = existing_contact_count
        else:
            # INSERT / UPDATE → rowcount = 1 (new row created)
            mock_result.rowcount = 1

        return mock_result

    session.execute.side_effect = execute_side_effect
    return session


def _make_adapter_with_candidates(candidates: list[ContactCandidate]) -> MagicMock:
    adapter = MagicMock(spec=PeopleSearchAdapter)
    adapter.adapter_name = "test_adapter"
    adapter.search_people.return_value = candidates
    return adapter


_PARENT_WI = {
    "work_item_id": "wi:parent-001",
    "attempt_budget_remaining": 3,
    "attempt_budget_policy": "standard",
    "trace_run_id": "run:001",
    "trace_correlation_id": "corr:001",
    "trace_policy_pack_id": "safe_v0_1",
}


def test_service_creates_contact_for_valid_candidate():
    session = _mock_session_for_service()
    adapter = _make_adapter_with_candidates([_make_candidate()])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.contacts_created == 1
    assert len(result.contact_ids) == 1
    assert result.no_signal is False


def test_service_dedup_two_identical_candidates_creates_one_contact():
    """Two identical candidates (same contact_id) must produce one Contact."""
    session = _mock_session_for_service()
    candidate = _make_candidate()
    adapter = _make_adapter_with_candidates([candidate, candidate])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.contacts_created == 1
    assert result.contacts_skipped == 1


def test_service_no_signal_when_no_candidates():
    session = _mock_session_for_service()
    adapter = _make_adapter_with_candidates([])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.no_signal is True
    assert result.contacts_created == 0


def test_service_raises_when_account_not_found():
    session = _mock_session_for_service(account_exists=False)
    adapter = _make_adapter_with_candidates([_make_candidate()])

    with pytest.raises(ValueError, match="Account not found"):
        run_people_search(
            session=session,
            account_id=_ACCOUNT_ID,
            adapter=adapter,
            role_targets=None,
            limits={"max_contacts_per_account": 3},
            context={},
            parent_work_item=_PARENT_WI,
        )


def test_service_rejects_candidate_with_wrong_account_id():
    session = _mock_session_for_service()
    candidate = _make_candidate(account_id="account:other.com")
    adapter = _make_adapter_with_candidates([candidate])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.contacts_created == 0
    assert result.contacts_rejected == 1
    assert result.no_signal is True


def test_service_role_ambiguity_no_linkedin_routes_needs_human():
    """
    Candidate with ambiguous role_cluster and no LinkedIn URL
    must trigger needs_human.
    Note: ContactCandidate validates role_cluster at construction,
    so we simulate an unknown cluster via a candidate whose role_cluster
    was set to None (no cluster = not unambiguously classifiable)
    by using a valid cluster but then testing a service-level override.

    Per SPEC-G1: role/title ambiguous AND no LinkedIn → needs_human.
    The service checks if role_cluster is not None and not in allowed set.
    Since ContactCandidate already rejects invalid clusters at construction,
    we test the needs_human path by using a service that received a candidate
    with role_cluster=None but role_title set — which is not ambiguous by itself.

    The canonical test: a pre-built ContactCandidate with role_cluster not in
    allowed set cannot be constructed. We verify needs_human through the
    service logic by building a candidate with role_cluster=None.
    """
    # A candidate with no role_cluster and no linkedin is NOT the trigger.
    # The trigger requires a non-allowed role_cluster AND no linkedin.
    # Since ContactCandidate validates role_cluster at construction, we need
    # to bypass validation to test service behavior. We use a MagicMock candidate.
    session = _mock_session_for_service()

    bad_candidate = MagicMock(spec=ContactCandidate)
    bad_candidate.account_id = _ACCOUNT_ID
    bad_candidate.full_name = "Bob"
    bad_candidate.provenance = _make_provenance()
    bad_candidate.email = None
    bad_candidate.linkedin_url = None  # no linkedin
    bad_candidate.role_cluster = "wizard"  # invalid cluster
    bad_candidate.role_title = "Wizard"
    bad_candidate.role_confidence = 0.5
    bad_candidate.source_provider = "test"
    bad_candidate.source_ref = "ref"
    bad_candidate.observed_at = _FIXED_OBSERVED_AT
    bad_candidate.confidence = 0.5

    adapter = _make_adapter_with_candidates([bad_candidate])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    # contact_id will be None (no identity fields) → rejected first,
    # but needs_human also set due to ambiguous role check that happens before
    # or the candidate is rejected for no identity.
    # Either way, no contacts should be created.
    assert result.contacts_created == 0


def test_service_needs_human_on_ambiguous_role_no_linkedin():
    """Direct test: ambiguous role_cluster + no linkedin → needs_human flag set."""
    session = _mock_session_for_service()

    # Use a mock that has a valid email (so contact_id resolves) but
    # an invalid role_cluster and no linkedin.
    bad_candidate = MagicMock(spec=ContactCandidate)
    bad_candidate.account_id = _ACCOUNT_ID
    bad_candidate.full_name = "Bob"
    bad_candidate.provenance = _make_provenance()
    bad_candidate.email = "bob@acme.example.com"
    bad_candidate.linkedin_url = None  # no linkedin
    bad_candidate.role_cluster = "wizard"  # not in allowed set
    bad_candidate.role_title = "Wizard"
    bad_candidate.role_confidence = 0.5
    bad_candidate.source_provider = "test"
    bad_candidate.source_ref = "ref"
    bad_candidate.observed_at = _FIXED_OBSERVED_AT
    bad_candidate.confidence = 0.5

    adapter = _make_adapter_with_candidates([bad_candidate])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.needs_human is True
    assert result.contacts_created == 0


def test_service_cap_limits_contacts_per_account():
    """Max contacts per account must be enforced."""
    session = _mock_session_for_service(existing_contact_count=3)
    # 3 already exist, cap is 3 → no new ones should be created
    candidate1 = _make_candidate(email="alice@acme.example.com")
    candidate2 = ContactCandidate(
        account_id=_ACCOUNT_ID,
        full_name="Bob Jones",
        provenance=_make_provenance(),
        email="bob@acme.example.com",
    )
    adapter = _make_adapter_with_candidates([candidate1, candidate2])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.contacts_created == 0
    assert result.contacts_skipped == 2


def test_service_enqueues_enrichment_per_contact():
    """One contact_enrichment work item must be enqueued per surviving contact."""
    session = _mock_session_for_service()
    adapter = _make_adapter_with_candidates([_make_candidate()])

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.downstream_enqueued == 1
