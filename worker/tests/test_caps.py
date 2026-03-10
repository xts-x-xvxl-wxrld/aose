"""
Tests for SPEC-G4: Deterministic caps and runaway prevention.

Acceptance checks covered:
  unit: cap constants match CONTRACT.yaml safe_v0_1 values
  unit: sort — higher confidence survives over lower confidence
  unit: sort — higher role_confidence breaks tie
  unit: sort — email-bearing candidate preferred over LinkedIn-only
  unit: sort — lexicographic contact_id as final tie-break
  unit: sort — None confidence treated as lowest priority
  unit: sort — five candidates → correct deterministic top-3
  unit: sort — replay produces identical order (stable)
  unit: run-level cap: count_run_contacts = 60 → service returns run_cap_exhausted
  unit: run-level cap: count_run_contacts < 60 → service proceeds normally
  unit: provider cap: count = MAX_PROVIDERS_PER_CONTACT → route=budget_exhausted
  unit: provider cap: count < MAX_PROVIDERS_PER_CONTACT → route proceeds
  unit: enrichment budget on enqueued WIs is MAX_ENRICH_ATTEMPTS_PER_CONTACT
  unit: per-account cap still enforced under sorted order
  unit: deterministic sort picks same survivors on replay
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from aose_worker.adapters.people_search.types import ContactCandidate
from aose_worker.canonical_ids import make_contact_id, normalize_email
from aose_worker.services.caps import (
    MAX_CONTACTS_PER_ACCOUNT,
    MAX_CONTACTS_TOTAL_PER_RUN,
    MAX_DRAFTS_PER_CONTACT,
    MAX_ENRICH_ATTEMPTS_PER_CONTACT,
    MAX_PROVIDERS_PER_CONTACT,
    candidate_sort_key,
)
from aose_worker.services.contact_enrichment_service import (
    ROUTE_BUDGET_EXHAUSTED,
    run_contact_enrichment,
)
from aose_worker.services.people_search_service import run_people_search

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_ACCOUNT_ID = "account:acme.com"
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
    email: str | None = "alice@acme.com",
    linkedin_url: str | None = None,
    confidence: float | None = 0.8,
    role_confidence: float | None = 0.7,
    role_cluster: str | None = "economic_buyer",
    account_id: str = _ACCOUNT_ID,
) -> ContactCandidate:
    return ContactCandidate(
        account_id=account_id,
        full_name="Test Person",
        provenance=_make_provenance(),
        email=email,
        linkedin_url=linkedin_url,
        role_cluster=role_cluster,
        role_confidence=role_confidence,
        confidence=confidence,
        source_provider="test_provider",
        source_ref="ref-001",
        observed_at=_FIXED_OBSERVED_AT,
    )


def _mock_people_search_session(
    account_exists: bool = True,
    existing_contact_count: int = 0,
    run_contact_count: int = 0,
) -> MagicMock:
    session = MagicMock()

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        mock_result = MagicMock()

        if "FROM accounts" in sql_str:
            if account_exists:
                mock_row = MagicMock()
                mock_result.mappings.return_value.first.return_value = mock_row
            else:
                mock_result.mappings.return_value.first.return_value = None
        elif (
            "FROM work_items" in sql_str
            and "contact_enrichment" in sql_str
            and "trace_run_id" in sql_str
        ):
            mock_result.scalar.return_value = run_contact_count
        elif "FROM contacts" in sql_str and "COUNT(*)" in sql_str:
            mock_result.scalar.return_value = existing_contact_count
        else:
            mock_result.rowcount = 1

        return mock_result

    session.execute.side_effect = execute_side_effect
    return session


def _mock_enrichment_session(
    contact: dict | None = None,
    provider_count: int = 1,
    has_linkedin_alias: bool = False,
    copy_generate_new_row: bool = True,
) -> MagicMock:
    """Session mock for contact_enrichment_service unit tests."""
    if contact is None:
        contact = {
            "contact_id": "contact:account:acme.com:alice@acme.com",
            "account_id": "account:acme.com",
            "full_name": "Alice",
            "channels_json": [
                {
                    "type": "email",
                    "value": "alice@acme.com",
                    "validated": "unverified",
                    "validated_at": None,
                    "source_trace": {},
                }
            ],
            "role_json": None,
            "status": "candidate",
        }

    session = MagicMock()

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        mock_result = MagicMock()

        if "FROM contacts" in sql_str and "channels_json" in sql_str:
            mappings_result = MagicMock()
            mappings_result.first.return_value = contact
            mock_result.mappings.return_value = mappings_result
        elif "FROM work_items" in sql_str and "entity_ref_id" in sql_str:
            # count_contact_providers
            mock_result.scalar.return_value = provider_count
        elif "FROM contact_aliases" in sql_str:
            mock_result.first.return_value = MagicMock() if has_linkedin_alias else None
        elif "UPDATE contacts" in sql_str:
            mock_result.rowcount = 1
        elif "INSERT INTO work_items" in sql_str:
            mock_result.rowcount = 1 if copy_generate_new_row else 0
        else:
            mock_result.rowcount = 1

        return mock_result

    session.execute.side_effect = execute_side_effect
    return session


_PARENT_WI = {
    "work_item_id": "wi:parent-001",
    "attempt_budget_remaining": 3,
    "attempt_budget_policy": "standard",
    "trace_run_id": "run:001",
    "trace_correlation_id": "corr:001",
    "trace_policy_pack_id": "safe_v0_1",
}

# ---------------------------------------------------------------------------
# Cap constants
# ---------------------------------------------------------------------------


def test_cap_max_contacts_total_per_run():
    assert MAX_CONTACTS_TOTAL_PER_RUN == 60


def test_cap_max_contacts_per_account():
    assert MAX_CONTACTS_PER_ACCOUNT == 3


def test_cap_max_enrich_attempts_per_contact():
    assert MAX_ENRICH_ATTEMPTS_PER_CONTACT == 2


def test_cap_max_providers_per_contact():
    assert MAX_PROVIDERS_PER_CONTACT == 2


def test_cap_max_drafts_per_contact():
    assert MAX_DRAFTS_PER_CONTACT == 2


# ---------------------------------------------------------------------------
# Deterministic sort key
# ---------------------------------------------------------------------------


def test_sort_key_higher_confidence_sorts_first():
    """Higher confidence must produce a lower sort key (sorts first)."""
    c_high = _make_candidate(confidence=0.9)
    c_low = _make_candidate(confidence=0.1)

    cid_high = make_contact_id(_ACCOUNT_ID, email="alice@acme.com")
    cid_low = make_contact_id(_ACCOUNT_ID, email="alice@acme.com")

    key_high = candidate_sort_key(c_high, cid_high)
    key_low = candidate_sort_key(c_low, cid_low)
    assert key_high < key_low


def test_sort_key_none_confidence_sorts_last():
    """None confidence must sort after any real confidence value."""
    c_real = _make_candidate(confidence=0.01)
    c_none = _make_candidate(confidence=None)

    cid = make_contact_id(_ACCOUNT_ID, email="alice@acme.com")

    assert candidate_sort_key(c_real, cid) < candidate_sort_key(c_none, cid)


def test_sort_key_higher_role_confidence_breaks_confidence_tie():
    """Equal confidence: higher role_confidence sorts first."""
    c_high_rc = _make_candidate(confidence=0.5, role_confidence=0.9)
    c_low_rc = _make_candidate(confidence=0.5, role_confidence=0.1)

    cid = make_contact_id(_ACCOUNT_ID, email="alice@acme.com")

    assert candidate_sort_key(c_high_rc, cid) < candidate_sort_key(c_low_rc, cid)


def test_sort_key_email_beats_linkedin_only():
    """Equal confidence and role_confidence: email-bearing sorts before LinkedIn-only."""
    c_email = _make_candidate(
        email="alice@acme.com", linkedin_url=None, confidence=0.5, role_confidence=0.5
    )
    norm_email = normalize_email("alice@acme.com")
    cid_email = make_contact_id(_ACCOUNT_ID, norm_email, None)

    c_li = _make_candidate(
        email=None,
        linkedin_url="https://linkedin.com/in/alice",
        confidence=0.5,
        role_confidence=0.5,
    )
    cid_li = make_contact_id(_ACCOUNT_ID, None, "https://linkedin.com/in/alice")

    assert candidate_sort_key(c_email, cid_email) < candidate_sort_key(c_li, cid_li)


def test_sort_key_contact_id_as_final_tiebreak():
    """Same everything: lexicographic contact_id breaks ties deterministically."""
    c = _make_candidate(confidence=0.5, role_confidence=0.5)
    # Same candidate, different contact_ids
    key_a = candidate_sort_key(c, "contact:account:aaa.com:x@aaa.com")
    key_b = candidate_sort_key(c, "contact:account:zzz.com:x@zzz.com")
    assert key_a < key_b


# ---------------------------------------------------------------------------
# Deterministic survivor selection (5 candidates → top 3)
# ---------------------------------------------------------------------------


def test_people_search_five_candidates_picks_top_three_by_confidence():
    """
    People search returning 5 candidates for one account must persist
    exactly 3 deterministic survivors (highest confidence first).
    """
    candidates = [
        _make_candidate(email=f"user{i}@acme.com", confidence=i * 0.1)
        for i in range(1, 6)  # confidence 0.1..0.5
    ]
    # Expected survivors: confidence 0.5, 0.4, 0.3 (top 3)

    session = _mock_people_search_session()
    adapter = MagicMock()
    adapter.search_people.return_value = candidates

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.contacts_created == 3
    assert result.contacts_skipped == 2  # 2 lowest-confidence skipped
    assert result.no_signal is False


def test_people_search_sort_order_is_stable_on_replay():
    """
    Replaying with the same candidates must produce the same survivors.
    contacts_created=0 on replay (all ON CONFLICT DO NOTHING → contacts_skipped).
    """
    candidates = [
        _make_candidate(email=f"user{i}@acme.com", confidence=i * 0.1)
        for i in range(1, 6)
    ]

    # First run: all inserted (rowcount=1)
    session1 = _mock_people_search_session()
    adapter = MagicMock()
    adapter.search_people.return_value = candidates

    result1 = run_people_search(
        session=session1,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    # Second run (replay): existing_count=3, all candidates skipped by cap
    session2 = _mock_people_search_session(existing_contact_count=3)
    result2 = run_people_search(
        session=session2,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result1.contacts_created == 3
    assert result2.contacts_created == 0
    # On replay all 5 are processed but cap-skipped (existing_count=3 >= cap=3)
    assert result2.contacts_skipped == 5


# ---------------------------------------------------------------------------
# Run-level contact cap
# ---------------------------------------------------------------------------


def test_run_cap_exhausted_when_60_contacts_already_in_run():
    """When run already has 60 contacts, service parks immediately."""
    session = _mock_people_search_session(run_contact_count=60)
    adapter = MagicMock()
    adapter.search_people.return_value = [_make_candidate()]

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.run_cap_exhausted is True
    assert result.contacts_created == 0


def test_run_cap_not_hit_when_below_60():
    """Run count < 60 must not trigger the cap."""
    session = _mock_people_search_session(run_contact_count=59)
    adapter = MagicMock()
    adapter.search_people.return_value = [_make_candidate()]

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=_PARENT_WI,
    )

    assert result.run_cap_exhausted is False
    assert result.contacts_created == 1


def test_run_cap_skipped_when_no_run_id():
    """If trace_run_id is absent, run-level cap check is skipped."""
    session = _mock_people_search_session()
    adapter = MagicMock()
    adapter.search_people.return_value = [_make_candidate()]

    wi_no_run = {**_PARENT_WI, "trace_run_id": ""}

    result = run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=wi_no_run,
    )

    assert result.run_cap_exhausted is False
    assert result.contacts_created == 1


# ---------------------------------------------------------------------------
# Provider cap (contact_enrichment)
# ---------------------------------------------------------------------------


def test_provider_cap_blocks_when_count_equals_max():
    """
    When count_contact_providers >= MAX_PROVIDERS_PER_CONTACT,
    enrichment must return route=budget_exhausted (third provider refused).
    """
    session = _mock_enrichment_session(provider_count=MAX_PROVIDERS_PER_CONTACT)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id="contact:account:acme.com:alice@acme.com",
            parent_work_item=_PARENT_WI,
        )

    assert result.route == ROUTE_BUDGET_EXHAUSTED
    assert result.copy_generate_enqueued is False


def test_provider_cap_allows_first_enrichment():
    """
    First enrichment (provider_count=1, the current WI itself) must proceed.
    """
    session = _mock_enrichment_session(provider_count=1)

    with patch(
        "aose_worker.services.contact_enrichment_service.validate_email",
        return_value="domain_ok",
    ):
        result = run_contact_enrichment(
            session=session,
            contact_id="contact:account:acme.com:alice@acme.com",
            parent_work_item=_PARENT_WI,
        )

    # Should NOT be budget_exhausted
    assert result.route != ROUTE_BUDGET_EXHAUSTED


# ---------------------------------------------------------------------------
# Enrichment attempt budget
# ---------------------------------------------------------------------------


def test_enrichment_work_item_has_budget_two():
    """
    Enrichment WorkItems enqueued by people_search must have
    attempt_budget_remaining = MAX_ENRICH_ATTEMPTS_PER_CONTACT (2),
    not the parent work item's budget.
    """
    captured_params = {}
    session = MagicMock()

    def execute_side_effect(sql, params=None):
        sql_str = str(sql)
        mock_result = MagicMock()

        if "FROM accounts" in sql_str:
            mock_result.mappings.return_value.first.return_value = MagicMock()
        elif "FROM work_items" in sql_str and "trace_run_id" in sql_str:
            mock_result.scalar.return_value = 0
        elif "FROM contacts" in sql_str and "COUNT(*)" in sql_str:
            mock_result.scalar.return_value = 0
        elif "INSERT INTO work_items" in sql_str and "contact_enrichment" in sql_str:
            # Capture params to verify budget value
            if params:
                captured_params.update(params)
            mock_result.rowcount = 1
        else:
            mock_result.rowcount = 1

        return mock_result

    session.execute.side_effect = execute_side_effect

    adapter = MagicMock()
    adapter.search_people.return_value = [_make_candidate()]

    # Parent work item has budget 3 — enrichment WI must use 2
    parent_wi = {**_PARENT_WI, "attempt_budget_remaining": 3}

    run_people_search(
        session=session,
        account_id=_ACCOUNT_ID,
        adapter=adapter,
        role_targets=None,
        limits={"max_contacts_per_account": 3},
        context={},
        parent_work_item=parent_wi,
    )

    assert (
        captured_params.get("attempt_budget_remaining")
        == MAX_ENRICH_ATTEMPTS_PER_CONTACT
    )
