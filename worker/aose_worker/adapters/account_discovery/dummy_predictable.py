"""
Dummy predictable adapter for Epic E account discovery.

Satisfies SPEC-E1 acceptance checks:
- No network access required.
- Deterministic output for the same query_object input.
- Stable provenance and evidence fields.
- Tests are independent of external provider availability.

Placeholder reference: PH-EPIC-E-001 — real adapter selection is deferred.
The dummy_predictable adapter is the required test adapter per CONTRACT.yaml
implementations_locked.required_test_adapter.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .base import AccountDiscoveryAdapter
from .types import (
    AccountDiscoveryCandidate,
    AccountDiscoveryResult,
    EvidencePointer,
    clamp_confidence,
    normalize_domain,
)

_ADAPTER_NAME = "dummy_predictable"
_ADAPTER_VERSION = "0.1.0"

# Fixed timestamp used for deterministic test output.
# Tests must not depend on wall-clock time.
_FIXED_OBSERVED_AT = "2026-01-01T00:00:00Z"

# Candidate templates — slot index is stable; same slot always produces
# structurally identical output for any given query_object_id.
_CANDIDATE_TEMPLATES: list[dict[str, Any]] = [
    {
        "legal_name": "Acme Software d.o.o.",
        "country": "SI",
        "registry_id": "1234567000",
        "domain": "www.acme-software.si",
        "legal_name_normalized": "acme software",
        "confidence_raw": 0.85,
        "source_provider": "dummy_registry",
        "evidence_source_type": "registry/api",
        "evidence_snippet": (
            "Acme Software d.o.o. registered at SI business registry. "
            "Status: active."
        ),
        "evidence_claim_frame": (
            "Legal entity exists and is active in SI business registry."
        ),
    },
    {
        "legal_name": "Beta Systems GmbH",
        "country": "DE",
        "registry_id": "HRB99001",
        "domain": "beta-systems.de",
        "legal_name_normalized": "beta systems",
        "confidence_raw": 0.78,
        "source_provider": "dummy_registry",
        "evidence_source_type": "registry/api",
        "evidence_snippet": (
            "Beta Systems GmbH listed in DE commercial register (Handelsregister)."
        ),
        "evidence_claim_frame": ("Legal entity exists in DE Handelsregister."),
    },
]


def _extract_query_object_id(query_object: Any) -> str:
    """Extract query_object_id from an ORM instance or a dict."""
    if isinstance(query_object, dict):
        return str(query_object["query_object_id"])
    return str(query_object.query_object_id)


def _make_source_ref(query_object_id: str, slot: int) -> str:
    """
    Return a deterministic source_ref for a given query_object_id and slot.

    Formula: first 16 hex chars of sha256("dummy_predictable|{qo_id}|{slot}")
    """
    raw = f"dummy_predictable|{query_object_id}|{slot}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _build_candidate(
    query_object_id: str,
    slot: int,
    template: dict[str, Any],
    observed_at: str,
) -> AccountDiscoveryCandidate:
    source_ref = _make_source_ref(query_object_id, slot)
    country = template["country"].upper()
    confidence = clamp_confidence(template["confidence_raw"])
    norm_domain = normalize_domain(template["domain"])

    candidate_provenance: dict[str, Any] = {
        "adapter": _ADAPTER_NAME,
        "query_object_id": query_object_id,
        "captured_at": observed_at,
        "slot": slot,
    }

    evidence_url = f"https://dummy-registry.local/entities/{source_ref}"
    ev = EvidencePointer(
        source_type=template["evidence_source_type"],
        url=evidence_url,
        captured_at=observed_at,
        snippet=template["evidence_snippet"],
        claim_frame=template["evidence_claim_frame"],
        provenance={
            "adapter": _ADAPTER_NAME,
            "query_object_id": query_object_id,
        },
    )

    return AccountDiscoveryCandidate(
        source_provider=template["source_provider"],
        source_ref=source_ref,
        observed_at=observed_at,
        confidence=confidence,
        legal_name=template["legal_name"],
        country=country,
        provenance=candidate_provenance,
        evidence=[ev],
        registry_id=template.get("registry_id"),
        domain=norm_domain,
        legal_name_normalized=template.get("legal_name_normalized"),
    )


class DummyPredictableAdapter(AccountDiscoveryAdapter):
    """
    Deterministic test adapter. No network access.

    Returns a fixed set of normalized candidates derived from the
    query_object_id. Two calls with identical inputs always produce
    structurally identical output.

    Placeholder: PH-EPIC-E-001 (real adapter selection deferred).
    """

    def search_accounts(
        self,
        query_object: Any,
        limits: dict[str, Any],
        context: dict[str, Any],
    ) -> AccountDiscoveryResult:
        qo_id = _extract_query_object_id(query_object)
        observed_at = context.get("observed_at_override") or _FIXED_OBSERVED_AT

        candidates = [
            _build_candidate(qo_id, slot, template, observed_at)
            for slot, template in enumerate(_CANDIDATE_TEMPLATES)
        ]

        return AccountDiscoveryResult(
            query_object_id=qo_id,
            adapter_name=_ADAPTER_NAME,
            adapter_version=_ADAPTER_VERSION,
            observed_at=observed_at,
            candidates=candidates,
        )
