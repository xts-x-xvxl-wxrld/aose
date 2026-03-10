from __future__ import annotations

from aose_worker.adapters.account_discovery.types import (
    AccountDiscoveryCandidate,
    EvidencePointer,
)
from aose_worker.services import account_discovery_service as svc
from aose_worker.services.dedup import (
    extract_account_trust_metadata,
    merge_evidence_ids,
    should_update_account,
)


def _candidate(
    *,
    country: str = "SI",
    registry_id: str | None = "1234567000",
    domain: str | None = "acme.si",
) -> AccountDiscoveryCandidate:
    return AccountDiscoveryCandidate(
        source_provider="dummy_registry",
        source_ref="abc123",
        observed_at="2026-01-01T00:00:00Z",
        confidence=0.8,
        legal_name="Acme d.o.o.",
        country=country,
        provenance={"adapter": "dummy_predictable"},
        evidence=[
            EvidencePointer(
                source_type="registry/api",
                url="https://example.test/acme",
                captured_at="2026-01-01T00:00:00Z",
                snippet="Acme listing",
                claim_frame="Entity exists",
                provenance={"adapter": "dummy_predictable", "query_object_id": "qo:1"},
            )
        ],
        registry_id=registry_id,
        domain=domain,
        legal_name_normalized="acme",
    )


def test_should_update_account_higher_trust_wins():
    assert should_update_account(
        existing_source_type="general_web_extracts",
        existing_captured_at="2026-01-01T00:00:00Z",
        existing_source_ref="z-ref",
        new_source_type="registry/api",
        new_captured_at="2025-01-01T00:00:00Z",
        new_source_ref="a-ref",
    )


def test_should_update_account_newer_capture_wins_when_trust_equal():
    assert should_update_account(
        existing_source_type="official_profiles",
        existing_captured_at="2026-01-01T00:00:00Z",
        existing_source_ref="z-ref",
        new_source_type="official_profiles",
        new_captured_at="2026-02-01T00:00:00Z",
        new_source_ref="a-ref",
    )


def test_should_update_account_lexicographic_tiebreak_on_source_ref():
    assert should_update_account(
        existing_source_type="official_profiles",
        existing_captured_at="2026-01-01T00:00:00Z",
        existing_source_ref="z-ref",
        new_source_type="official_profiles",
        new_captured_at="2026-01-01T00:00:00Z",
        new_source_ref="a-ref",
    )


def test_merge_evidence_ids_idempotent_and_order_preserving():
    existing = ["evidence:1", "evidence:2"]
    new = ["evidence:2", "evidence:3", "evidence:1", "evidence:4"]
    merged = merge_evidence_ids(existing, new)
    assert merged == ["evidence:1", "evidence:2", "evidence:3", "evidence:4"]
    assert merge_evidence_ids(merged, new) == merged


def test_extract_account_trust_metadata_supports_list_and_dict():
    p_list = [
        {
            "source_type": "registry/api",
            "captured_at": "2026-01-01T00:00:00Z",
            "source_ref": "x",
        }
    ]
    p_dict = {
        "source_type": "official_profiles",
        "captured_at": "2026-01-02T00:00:00Z",
        "source_ref": "y",
    }
    assert extract_account_trust_metadata(p_list) == (
        "registry/api",
        "2026-01-01T00:00:00Z",
        "x",
    )
    assert extract_account_trust_metadata(p_dict) == (
        "official_profiles",
        "2026-01-02T00:00:00Z",
        "y",
    )


def test_resolver_prefers_registry_alias_match(monkeypatch):
    candidate = _candidate()

    monkeypatch.setattr(svc, "_load_account_state", lambda _s, _id: None)

    def _find(_session, alias_type: str, alias_value: str) -> str | None:
        if alias_type == "registry" and alias_value == "SI-1234567000":
            return "account:SI-1234567000"
        return None

    monkeypatch.setattr(svc, "_find_account_id_by_alias", _find)

    resolved = svc._resolve_canonical_account_id(session=None, candidate=candidate)  # type: ignore[arg-type]
    assert resolved == "account:SI-1234567000"


def test_resolver_falls_back_to_domain_alias(monkeypatch):
    candidate = _candidate(registry_id=None, domain="acme.si")

    monkeypatch.setattr(svc, "_load_account_state", lambda _s, _id: None)

    def _find(_session, alias_type: str, alias_value: str) -> str | None:
        if alias_type == "domain" and alias_value == "acme.si":
            return "account:acme.si"
        return None

    monkeypatch.setattr(svc, "_find_account_id_by_alias", _find)

    resolved = svc._resolve_canonical_account_id(session=None, candidate=candidate)  # type: ignore[arg-type]
    assert resolved == "account:acme.si"


def test_resolver_falls_back_to_tmp_when_no_registry_or_domain(monkeypatch):
    candidate = _candidate(country="SI", registry_id=None, domain=None)

    monkeypatch.setattr(svc, "_load_account_state", lambda _s, _id: None)
    monkeypatch.setattr(svc, "_find_account_id_by_alias", lambda *_a, **_k: None)

    resolved = svc._resolve_canonical_account_id(session=None, candidate=candidate)  # type: ignore[arg-type]
    assert resolved.startswith("account:tmp:")
