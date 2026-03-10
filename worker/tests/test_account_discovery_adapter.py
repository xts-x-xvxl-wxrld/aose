"""
Unit tests for SPEC-E1: AccountDiscoveryAdapter interface + dummy adapter.

Acceptance checks covered:
  1. unit: result object matches interface schema
  2. unit: dummy adapter returns predictable normalized candidates
  3. unit: domain normalization is applied at adapter output boundary
  4. unit: confidence remains within 0.0..1.0
  5. unit: evidence objects are structured, not prose-only
  6. DummyPredictableAdapter implements AccountDiscoveryAdapter (ABC)
  7. Validation rejects malformed candidates/results/evidence
"""

import pytest

from aose_worker.adapters.account_discovery.base import AccountDiscoveryAdapter
from aose_worker.adapters.account_discovery.dummy_predictable import (
    DummyPredictableAdapter,
)
from aose_worker.adapters.account_discovery.types import (
    AccountDiscoveryCandidate,
    AccountDiscoveryResult,
    EvidencePointer,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_QUERY_OBJECT = {
    "query_object_id": "qo:test-001",
    "seller_id": "seller:test",
    "buyer_context": "B2B SaaS HR software",
    "keywords": ["hr", "saas"],
    "exclusions": [],
    "priority": 1.0,
}
_LIMITS: dict = {"max_accounts": 10, "max_external_calls": 250}
_CONTEXT: dict = {}


@pytest.fixture
def adapter() -> DummyPredictableAdapter:
    return DummyPredictableAdapter()


@pytest.fixture
def result(adapter: DummyPredictableAdapter) -> AccountDiscoveryResult:
    return adapter.search_accounts(_QUERY_OBJECT, _LIMITS, _CONTEXT)


# ---------------------------------------------------------------------------
# Interface conformance
# ---------------------------------------------------------------------------


def test_dummy_adapter_implements_base_interface():
    """DummyPredictableAdapter must be an instance of AccountDiscoveryAdapter."""
    assert isinstance(DummyPredictableAdapter(), AccountDiscoveryAdapter)


def test_result_is_account_discovery_result(result: AccountDiscoveryResult):
    """search_accounts must return an AccountDiscoveryResult."""
    assert isinstance(result, AccountDiscoveryResult)


def test_result_required_fields_present(result: AccountDiscoveryResult):
    """All required result fields must be populated."""
    assert result.query_object_id == "qo:test-001"
    assert result.adapter_name
    assert result.adapter_version
    assert result.observed_at
    assert isinstance(result.candidates, list)


def test_result_contains_candidates(result: AccountDiscoveryResult):
    """Dummy adapter must return at least one candidate."""
    assert len(result.candidates) > 0


# ---------------------------------------------------------------------------
# Determinism (SPEC-E1 acceptance: predictable normalized candidates)
# ---------------------------------------------------------------------------


def test_deterministic_output_same_input(adapter: DummyPredictableAdapter):
    """Repeating the same call returns structurally identical candidates."""
    r1 = adapter.search_accounts(_QUERY_OBJECT, _LIMITS, _CONTEXT)
    r2 = adapter.search_accounts(_QUERY_OBJECT, _LIMITS, _CONTEXT)

    assert len(r1.candidates) == len(r2.candidates)
    for c1, c2 in zip(r1.candidates, r2.candidates):
        assert c1.source_ref == c2.source_ref
        assert c1.legal_name == c2.legal_name
        assert c1.country == c2.country
        assert c1.confidence == c2.confidence
        assert c1.domain == c2.domain


def test_different_query_object_id_produces_different_source_refs(
    adapter: DummyPredictableAdapter,
):
    """Different query_object_id must produce different source_refs."""
    r1 = adapter.search_accounts(_QUERY_OBJECT, _LIMITS, _CONTEXT)
    other_qo = dict(_QUERY_OBJECT, query_object_id="qo:other-999")
    r2 = adapter.search_accounts(other_qo, _LIMITS, _CONTEXT)

    refs_r1 = {c.source_ref for c in r1.candidates}
    refs_r2 = {c.source_ref for c in r2.candidates}
    assert refs_r1.isdisjoint(refs_r2)


# ---------------------------------------------------------------------------
# Required candidate fields
# ---------------------------------------------------------------------------


def test_candidates_carry_required_fields(result: AccountDiscoveryResult):
    """Every candidate must carry all required contract fields."""
    for c in result.candidates:
        assert c.source_provider
        assert c.source_ref
        assert c.observed_at
        assert c.legal_name
        assert c.country
        assert isinstance(c.provenance, dict)
        assert isinstance(c.evidence, list)
        assert len(c.evidence) > 0


# ---------------------------------------------------------------------------
# Normalization checks (SPEC-E1 required)
# ---------------------------------------------------------------------------


def test_country_codes_are_uppercase(result: AccountDiscoveryResult):
    """country must be an uppercase ISO-like code per CONTRACT.yaml."""
    for c in result.candidates:
        assert c.country == c.country.upper(), f"country {c.country!r} is not uppercase"


def test_confidence_within_bounds(result: AccountDiscoveryResult):
    """confidence must be in [0.0, 1.0] for all candidates."""
    for c in result.candidates:
        assert 0.0 <= c.confidence <= 1.0, f"confidence {c.confidence} is out of bounds"


def test_domain_normalization_applied(result: AccountDiscoveryResult):
    """
    domain must be normalized at adapter output boundary.
    Normalized domain has no www. prefix and is lowercase.
    """
    for c in result.candidates:
        if c.domain is not None:
            assert not c.domain.startswith(
                "www."
            ), f"domain {c.domain!r} has www. prefix — normalization not applied"
            assert c.domain == c.domain.lower(), f"domain {c.domain!r} is not lowercase"


# ---------------------------------------------------------------------------
# Evidence structure (SPEC-E1: evidence objects must be structured)
# ---------------------------------------------------------------------------


def test_evidence_objects_are_evidence_pointer_instances(
    result: AccountDiscoveryResult,
):
    """Evidence must be EvidencePointer instances, not plain strings or dicts."""
    for c in result.candidates:
        for ev in c.evidence:
            assert isinstance(ev, EvidencePointer)


def test_evidence_carries_required_pointer_fields(result: AccountDiscoveryResult):
    """Every EvidencePointer must carry source_type, url, captured_at, snippet,
    claim_frame, and provenance."""
    for c in result.candidates:
        for ev in c.evidence:
            assert ev.source_type
            assert ev.url
            assert ev.captured_at
            assert ev.snippet
            assert ev.claim_frame
            assert isinstance(ev.provenance, dict)


def test_evidence_provenance_includes_adapter_and_query_object_id(
    result: AccountDiscoveryResult,
):
    """Evidence provenance must include adapter and query_object_id fields."""
    for c in result.candidates:
        for ev in c.evidence:
            assert "adapter" in ev.provenance
            assert "query_object_id" in ev.provenance


# ---------------------------------------------------------------------------
# Candidate provenance fields (CONTRACT.yaml provenance_required_on_account)
# ---------------------------------------------------------------------------


def test_candidate_provenance_has_required_fields(result: AccountDiscoveryResult):
    """Candidate provenance must carry adapter, query_object_id, captured_at."""
    for c in result.candidates:
        assert "adapter" in c.provenance
        assert "query_object_id" in c.provenance
        assert "captured_at" in c.provenance


# ---------------------------------------------------------------------------
# Validation enforcement — malformed input must raise ValueError
# ---------------------------------------------------------------------------


def _valid_evidence() -> EvidencePointer:
    return EvidencePointer(
        source_type="registry/api",
        url="https://example.com/entity/001",
        captured_at="2026-01-01T00:00:00Z",
        snippet="Company registered and active.",
        claim_frame="Legal entity exists in registry.",
        provenance={"adapter": "test", "query_object_id": "qo:x"},
    )


def _valid_provenance() -> dict:
    return {
        "adapter": "test",
        "query_object_id": "qo:x",
        "captured_at": "2026-01-01T00:00:00Z",
    }


def test_evidence_pointer_rejects_empty_source_type():
    with pytest.raises(ValueError, match="source_type"):
        EvidencePointer(
            source_type="",
            url="https://example.com",
            captured_at="2026-01-01T00:00:00Z",
            snippet="test",
            claim_frame="test",
            provenance={"adapter": "test"},
        )


def test_evidence_pointer_rejects_empty_url():
    with pytest.raises(ValueError, match="url"):
        EvidencePointer(
            source_type="registry/api",
            url="",
            captured_at="2026-01-01T00:00:00Z",
            snippet="test",
            claim_frame="test",
            provenance={"adapter": "test"},
        )


def test_candidate_rejects_confidence_above_one():
    with pytest.raises(ValueError, match="confidence"):
        AccountDiscoveryCandidate(
            source_provider="test",
            source_ref="ref001",
            observed_at="2026-01-01T00:00:00Z",
            confidence=1.5,
            legal_name="Test Corp",
            country="US",
            provenance=_valid_provenance(),
            evidence=[_valid_evidence()],
        )


def test_candidate_rejects_confidence_below_zero():
    with pytest.raises(ValueError, match="confidence"):
        AccountDiscoveryCandidate(
            source_provider="test",
            source_ref="ref001",
            observed_at="2026-01-01T00:00:00Z",
            confidence=-0.1,
            legal_name="Test Corp",
            country="US",
            provenance=_valid_provenance(),
            evidence=[_valid_evidence()],
        )


def test_candidate_rejects_lowercase_country():
    with pytest.raises(ValueError, match="uppercase"):
        AccountDiscoveryCandidate(
            source_provider="test",
            source_ref="ref001",
            observed_at="2026-01-01T00:00:00Z",
            confidence=0.5,
            legal_name="Test Corp",
            country="us",
            provenance=_valid_provenance(),
            evidence=[_valid_evidence()],
        )


def test_candidate_rejects_empty_evidence_list():
    with pytest.raises(ValueError, match="evidence"):
        AccountDiscoveryCandidate(
            source_provider="test",
            source_ref="ref001",
            observed_at="2026-01-01T00:00:00Z",
            confidence=0.5,
            legal_name="Test Corp",
            country="US",
            provenance=_valid_provenance(),
            evidence=[],
        )


def test_result_rejects_empty_query_object_id():
    with pytest.raises(ValueError, match="query_object_id"):
        AccountDiscoveryResult(
            query_object_id="",
            adapter_name="test",
            adapter_version="0.1",
            observed_at="2026-01-01T00:00:00Z",
        )


def test_result_rejects_empty_adapter_name():
    with pytest.raises(ValueError, match="adapter_name"):
        AccountDiscoveryResult(
            query_object_id="qo:x",
            adapter_name="",
            adapter_version="0.1",
            observed_at="2026-01-01T00:00:00Z",
        )
