"""
Tests for SPEC-H1: Evidence digest builder.

Acceptance checks covered:
  unit: build_evidence_digest — required shape fields are present
  unit: build_evidence_digest — seller_summary has seller_id, offer, constraints
  unit: build_evidence_digest — account_summary has account_id, name, domain, country
  unit: build_evidence_digest — contact_summary has contact_id, full_name, role, channels
  unit: build_evidence_digest — evidence_items have all required fields
  unit: build_evidence_digest — drafting_constraints has policy_pack_id, avoid_claims, allowed_channels, language
  unit: evidence ordering — trust descending is primary sort
  unit: evidence ordering — captured_at descending is secondary sort when trust equal
  unit: evidence ordering — evidence_id lexicographic is tiebreak
  unit: evidence ordering — unknown source_type sorts last
  unit: contract error — missing seller → DigestContractError
  unit: contract error — missing account → DigestContractError
  unit: contract error — missing contact → DigestContractError
  unit: contract error — missing evidence_id → DigestContractError
  unit: contract error — empty evidence_ids → DigestContractError
  unit: digest does not mutate canonical records
  unit: _source_trust order is deterministic
  unit: language propagates to drafting_constraints
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock

import pytest

from aose_worker.services.evidence_digest_service import (
    DigestContractError,
    EvidenceDigest,
    _row_sort_key,
    _source_trust,
    build_evidence_digest,
)

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_SELLER_ID = "seller:test-seller-01"
_ACCOUNT_ID = "account:acme.com"
_CONTACT_ID = "contact:acme.com:ct-001"

_DT_RECENT = datetime(2025, 6, 1, tzinfo=timezone.utc)
_DT_OLDER = datetime(2024, 1, 1, tzinfo=timezone.utc)
_DT_OLDEST = datetime(2023, 1, 1, tzinfo=timezone.utc)


def _make_seller_row() -> dict[str, Any]:
    return {
        "seller_id": _SELLER_ID,
        "offer_what": "CRM software",
        "offer_where": ["Slovenia", "Croatia"],
        "offer_who": ["SMB"],
        "offer_positioning": ["affordable"],
        "constraints_avoid_claims": ["no ROI guarantees"],
        "constraints_allowed_channels": ["email"],
        "constraints_languages": ["en", "de"],
        "policy_pack_id": "safe_v0_1",
    }


def _make_account_row() -> dict[str, Any]:
    return {
        "account_id": _ACCOUNT_ID,
        "name": "Acme Corp",
        "domain": "acme.com",
        "country": "US",
    }


def _make_contact_row() -> dict[str, Any]:
    return {
        "contact_id": _CONTACT_ID,
        "full_name": "Alice Smith",
        "role_json": {"cluster": "economic_buyer", "title": "CEO"},
        "channels_json": [{"type": "email", "value": "a@acme.com"}],
    }


def _make_evidence_row(
    eid: str,
    source_type: str = "general web extracts",
    captured_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "evidence_id": eid,
        "source_type": source_type,
        "canonical_url": f"https://example.com/{eid}",
        "captured_at": captured_at or _DT_RECENT,
        "claim_frame": f"claim for {eid}",
        "snippet": f"snippet for {eid}",
    }


def _build_session(
    seller: dict | None = None,
    account: dict | None = None,
    contact: dict | None = None,
    evidence_map: dict[str, dict] | None = None,
) -> MagicMock:
    """
    Build a mock SQLAlchemy Session whose execute().mappings().first()
    returns the appropriate row for each table query.
    """
    seller_row = seller or _make_seller_row()
    account_row = account or _make_account_row()
    contact_row = contact or _make_contact_row()
    evidence_map = evidence_map or {}

    def execute_side_effect(sql, params=None):
        params = params or {}
        sql_text = str(sql)
        mock_result = MagicMock()
        mapping_result = MagicMock()

        if "seller_profiles" in sql_text:
            if params.get("id") == seller_row.get("seller_id"):
                mapping_result.first.return_value = seller_row
            else:
                mapping_result.first.return_value = None
        elif "FROM accounts" in sql_text:
            if params.get("id") == account_row.get("account_id"):
                mapping_result.first.return_value = account_row
            else:
                mapping_result.first.return_value = None
        elif "FROM contacts" in sql_text:
            if params.get("id") == contact_row.get("contact_id"):
                mapping_result.first.return_value = contact_row
            else:
                mapping_result.first.return_value = None
        elif "FROM evidence" in sql_text:
            eid = params.get("id")
            row = evidence_map.get(eid)
            mapping_result.first.return_value = row
        else:
            mapping_result.first.return_value = None

        mock_result.mappings.return_value = mapping_result
        return mock_result

    session = MagicMock()
    session.execute.side_effect = execute_side_effect
    return session


# ---------------------------------------------------------------------------
# Source trust order
# ---------------------------------------------------------------------------


def test_source_trust_registry_api_highest():
    assert _source_trust("registry/api") > _source_trust("first-party site")


def test_source_trust_order_descending():
    order = [
        "registry/api",
        "first-party site",
        "official profiles",
        "reputable directories",
        "general web extracts",
    ]
    for i in range(len(order) - 1):
        assert _source_trust(order[i]) > _source_trust(order[i + 1])


def test_source_trust_unknown_sorts_last():
    assert _source_trust("unknown-source") < _source_trust("general web extracts")


# ---------------------------------------------------------------------------
# Ordering: _row_sort_key
# ---------------------------------------------------------------------------


def test_row_sort_key_trust_primary():
    high = _make_evidence_row("ev:1", source_type="registry/api", captured_at=_DT_OLDER)
    low = _make_evidence_row(
        "ev:2", source_type="general web extracts", captured_at=_DT_RECENT
    )
    # High trust sorts earlier (lower sort key) even though captured_at is older
    assert _row_sort_key(high) < _row_sort_key(low)


def test_row_sort_key_captured_at_secondary():
    row_recent = _make_evidence_row(
        "ev:a", source_type="general web extracts", captured_at=_DT_RECENT
    )
    row_older = _make_evidence_row(
        "ev:b", source_type="general web extracts", captured_at=_DT_OLDER
    )
    # Same trust → recent captured_at sorts earlier (lower sort key)
    assert _row_sort_key(row_recent) < _row_sort_key(row_older)


def test_row_sort_key_evidence_id_tiebreak():
    row_a = _make_evidence_row(
        "ev:aaa", source_type="general web extracts", captured_at=_DT_RECENT
    )
    row_b = _make_evidence_row(
        "ev:bbb", source_type="general web extracts", captured_at=_DT_RECENT
    )
    # Same trust + same captured_at → evidence_id lexicographic ascending
    assert _row_sort_key(row_a) < _row_sort_key(row_b)


# ---------------------------------------------------------------------------
# Happy path: required shape
# ---------------------------------------------------------------------------


def test_build_digest_returns_evidence_digest():
    ev_id = "evidence:abc123"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    result = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    assert isinstance(result, EvidenceDigest)


def test_seller_summary_required_fields():
    ev_id = "evidence:abc123"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    ss = digest.seller_summary
    assert ss.seller_id == _SELLER_ID
    assert "what" in ss.offer
    assert "avoid_claims" in ss.constraints


def test_account_summary_required_fields():
    ev_id = "evidence:abc123"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    acct = digest.account_summary
    assert acct.account_id == _ACCOUNT_ID
    assert acct.name == "Acme Corp"
    assert acct.domain == "acme.com"
    assert acct.country == "US"


def test_contact_summary_required_fields():
    ev_id = "evidence:abc123"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    cs = digest.contact_summary
    assert cs.contact_id == _CONTACT_ID
    assert cs.full_name == "Alice Smith"
    assert isinstance(cs.role, dict)
    assert isinstance(cs.channels, list)


def test_evidence_items_required_fields():
    ev_id = "evidence:abc123"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    assert len(digest.evidence_items) == 1
    item = digest.evidence_items[0]
    assert item.evidence_id == ev_id
    assert item.source_type == "general web extracts"
    assert item.url.startswith("https://")
    assert item.captured_at  # non-empty ISO string
    assert item.claim_frame
    assert item.snippet


def test_drafting_constraints_required_fields():
    ev_id = "evidence:abc123"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    dc = digest.drafting_constraints
    assert dc.policy_pack_id == "safe_v0_1"
    assert isinstance(dc.avoid_claims, list)
    assert isinstance(dc.allowed_channels, list)
    assert dc.language == "en"


def test_language_propagates_to_drafting_constraints():
    ev_id = "evidence:de001"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
        language="de",
    )
    assert digest.drafting_constraints.language == "de"


# ---------------------------------------------------------------------------
# Ordering: integration with build_evidence_digest
# ---------------------------------------------------------------------------


def test_evidence_ordering_trust_descending():
    ev1 = "ev:trust-low"
    ev2 = "ev:trust-high"
    evidence_map = {
        ev1: _make_evidence_row(
            ev1, source_type="general web extracts", captured_at=_DT_RECENT
        ),
        ev2: _make_evidence_row(ev2, source_type="registry/api", captured_at=_DT_OLDER),
    }
    session = _build_session(evidence_map=evidence_map)
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev1, ev2],
    )
    # registry/api (high trust) must come first even though captured_at is older
    assert digest.evidence_items[0].evidence_id == ev2
    assert digest.evidence_items[1].evidence_id == ev1


def test_evidence_ordering_captured_at_descending_when_trust_equal():
    ev_recent = "ev:recent"
    ev_older = "ev:older"
    evidence_map = {
        ev_recent: _make_evidence_row(
            ev_recent, source_type="general web extracts", captured_at=_DT_RECENT
        ),
        ev_older: _make_evidence_row(
            ev_older, source_type="general web extracts", captured_at=_DT_OLDER
        ),
    }
    session = _build_session(evidence_map=evidence_map)
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_older, ev_recent],  # intentionally reversed input order
    )
    assert digest.evidence_items[0].evidence_id == ev_recent
    assert digest.evidence_items[1].evidence_id == ev_older


def test_evidence_ordering_evidence_id_tiebreak():
    ev_a = "ev:aaa"
    ev_b = "ev:bbb"
    evidence_map = {
        ev_a: _make_evidence_row(
            ev_a, source_type="general web extracts", captured_at=_DT_RECENT
        ),
        ev_b: _make_evidence_row(
            ev_b, source_type="general web extracts", captured_at=_DT_RECENT
        ),
    }
    session = _build_session(evidence_map=evidence_map)
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_b, ev_a],  # intentionally reversed
    )
    assert digest.evidence_items[0].evidence_id == ev_a
    assert digest.evidence_items[1].evidence_id == ev_b


def test_evidence_ordering_full_three_key():
    """Three evidence items exercising all three sort levels."""
    ev_high_trust = "ev:z-high-trust"
    ev_recent = "ev:a-recent"
    ev_older = "ev:b-older"
    evidence_map = {
        ev_high_trust: _make_evidence_row(ev_high_trust, "registry/api", _DT_OLDEST),
        ev_recent: _make_evidence_row(ev_recent, "general web extracts", _DT_RECENT),
        ev_older: _make_evidence_row(ev_older, "general web extracts", _DT_OLDER),
    }
    session = _build_session(evidence_map=evidence_map)
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_older, ev_recent, ev_high_trust],
    )
    ids = [item.evidence_id for item in digest.evidence_items]
    assert ids[0] == ev_high_trust  # trust=4 wins
    assert ids[1] == ev_recent  # same trust as ev_older but more recent
    assert ids[2] == ev_older


# ---------------------------------------------------------------------------
# Contract error cases
# ---------------------------------------------------------------------------


def test_missing_seller_raises_digest_contract_error():
    ev_id = "ev:x"
    session = _build_session(
        seller={"seller_id": "seller:other"},  # different ID
        evidence_map={ev_id: _make_evidence_row(ev_id)},
    )
    with pytest.raises(DigestContractError, match="SellerProfile not found"):
        build_evidence_digest(
            session=session,
            seller_id=_SELLER_ID,
            account_id=_ACCOUNT_ID,
            contact_id=_CONTACT_ID,
            evidence_ids=[ev_id],
        )


def test_missing_account_raises_digest_contract_error():
    ev_id = "ev:x"
    session = _build_session(
        account={"account_id": "account:other"},
        evidence_map={ev_id: _make_evidence_row(ev_id)},
    )
    with pytest.raises(DigestContractError, match="Account not found"):
        build_evidence_digest(
            session=session,
            seller_id=_SELLER_ID,
            account_id=_ACCOUNT_ID,
            contact_id=_CONTACT_ID,
            evidence_ids=[ev_id],
        )


def test_missing_contact_raises_digest_contract_error():
    ev_id = "ev:x"
    session = _build_session(
        contact={"contact_id": "contact:other"},
        evidence_map={ev_id: _make_evidence_row(ev_id)},
    )
    with pytest.raises(DigestContractError, match="Contact not found"):
        build_evidence_digest(
            session=session,
            seller_id=_SELLER_ID,
            account_id=_ACCOUNT_ID,
            contact_id=_CONTACT_ID,
            evidence_ids=[ev_id],
        )


def test_missing_evidence_id_raises_digest_contract_error():
    session = _build_session(evidence_map={})  # evidence_map is empty
    with pytest.raises(DigestContractError, match="Evidence not found"):
        build_evidence_digest(
            session=session,
            seller_id=_SELLER_ID,
            account_id=_ACCOUNT_ID,
            contact_id=_CONTACT_ID,
            evidence_ids=["ev:nonexistent"],
        )


def test_empty_evidence_ids_raises_digest_contract_error():
    session = _build_session()
    with pytest.raises(
        DigestContractError, match="evidence_ids must be a non-empty list"
    ):
        build_evidence_digest(
            session=session,
            seller_id=_SELLER_ID,
            account_id=_ACCOUNT_ID,
            contact_id=_CONTACT_ID,
            evidence_ids=[],
        )


# ---------------------------------------------------------------------------
# Invariants: no mutation, no provider credentials in output
# ---------------------------------------------------------------------------


def test_digest_does_not_mutate_session():
    ev_id = "ev:abc"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    # No UPDATE / INSERT calls should have been made
    for call in session.execute.call_args_list:
        sql_text = str(call.args[0]).upper()
        assert "UPDATE" not in sql_text
        assert "INSERT" not in sql_text


def test_digest_contains_only_canonical_fields():
    """Verify no provider credentials or unexpected keys appear in digest."""
    ev_id = "ev:abc"
    session = _build_session(evidence_map={ev_id: _make_evidence_row(ev_id)})
    digest = build_evidence_digest(
        session=session,
        seller_id=_SELLER_ID,
        account_id=_ACCOUNT_ID,
        contact_id=_CONTACT_ID,
        evidence_ids=[ev_id],
    )
    # Seller summary should not expose raw DB column names
    assert not hasattr(digest.seller_summary, "offer_what")
    assert not hasattr(digest.seller_summary, "constraints_avoid_claims")
    # Evidence items should not contain provenance_json or source_provider secrets
    item = digest.evidence_items[0]
    assert not hasattr(item, "provenance_json")
    assert not hasattr(item, "source_provider")
