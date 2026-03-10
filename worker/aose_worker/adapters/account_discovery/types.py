"""
Typed shapes for the AccountDiscovery adapter interface.

All shapes enforce the Epic E adapter contract at construction time.
Normalization (domain, country, confidence) must be applied at the
adapter boundary before constructing these objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Local domain normalization
# Mirrors aose_api.ids.normalize_domain for use within the worker package.
# The worker does not import from aose_api to preserve service isolation.
# ---------------------------------------------------------------------------


def normalize_domain(value: str | None) -> str | None:
    """
    Normalize a domain name or URL to canonical lowercase ASCII host.

    Rules match the Epic B helper in aose_api.ids:
    - Trim whitespace; parse host from URL if scheme present
    - Lowercase, remove port, remove trailing dot
    - Strip exactly one leading "www."
    - Convert to IDNA ASCII
    - Return None for empty or invalid input
    """
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    if "://" in value or value.startswith("//"):
        parsed = urlparse(value)
        host = parsed.hostname
    else:
        parsed = urlparse("https://" + value)
        host = parsed.hostname

    if not host:
        return None

    host = host.rstrip(".")

    if host.startswith("www."):
        host = host[4:]

    if not host:
        return None

    try:
        host = host.encode("idna").decode("ascii")
    except (UnicodeError, UnicodeDecodeError):
        return None

    return host if host else None


def clamp_confidence(value: float) -> float:
    """Clamp confidence to the closed interval [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


# ---------------------------------------------------------------------------
# Evidence pointer shape
# ---------------------------------------------------------------------------


@dataclass
class EvidencePointer:
    """
    Structured evidence pointer suitable for later canonical Evidence mapping.

    Prose-only evidence is forbidden by CONTRACT.yaml. Each instance must
    carry structured pointer fields: source_type, url, captured_at, snippet,
    claim_frame, and provenance.
    """

    source_type: str
    url: str
    captured_at: str  # ISO 8601
    snippet: str
    claim_frame: str
    provenance: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.source_type:
            raise ValueError("EvidencePointer.source_type is required")
        if not self.url:
            raise ValueError("EvidencePointer.url is required")
        if not self.captured_at:
            raise ValueError("EvidencePointer.captured_at is required")
        if not self.snippet:
            raise ValueError("EvidencePointer.snippet is required")
        if not self.claim_frame:
            raise ValueError("EvidencePointer.claim_frame is required")
        if not isinstance(self.provenance, dict):
            raise ValueError("EvidencePointer.provenance must be a dict")


# ---------------------------------------------------------------------------
# Candidate shape
# ---------------------------------------------------------------------------


@dataclass
class AccountDiscoveryCandidate:
    """
    Normalized candidate returned by an AccountDiscoveryAdapter.

    Required fields enforce the Epic E adapter contract.
    Normalization invariants that must hold at construction:
    - country must already be an uppercase ISO-like code
    - domain must already be normalized (if present)
    - confidence must already be clamped to [0.0, 1.0]
    - evidence must contain at least one structured EvidencePointer
    """

    # Required fields (CONTRACT.yaml candidate_shape.required_fields)
    source_provider: str
    source_ref: str
    observed_at: str  # ISO 8601
    confidence: float  # must be in [0.0, 1.0]
    legal_name: str
    country: str  # uppercase ISO-like
    provenance: dict[str, Any]
    evidence: list[EvidencePointer]

    # Optional fields (CONTRACT.yaml candidate_shape.optional_fields)
    registry_id: str | None = None
    domain: str | None = None  # normalized
    legal_name_normalized: str | None = None
    raw_payload_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.source_provider:
            raise ValueError("AccountDiscoveryCandidate.source_provider is required")
        if not self.source_ref:
            raise ValueError("AccountDiscoveryCandidate.source_ref is required")
        if not self.observed_at:
            raise ValueError("AccountDiscoveryCandidate.observed_at is required")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"AccountDiscoveryCandidate.confidence must be in [0.0, 1.0],"
                f" got {self.confidence}"
            )
        if not self.legal_name:
            raise ValueError("AccountDiscoveryCandidate.legal_name is required")
        if not self.country:
            raise ValueError("AccountDiscoveryCandidate.country is required")
        if self.country != self.country.upper():
            raise ValueError(
                f"AccountDiscoveryCandidate.country must be uppercase ISO-like code,"
                f" got {self.country!r}"
            )
        if not isinstance(self.provenance, dict):
            raise ValueError("AccountDiscoveryCandidate.provenance must be a dict")
        if not isinstance(self.evidence, list) or len(self.evidence) == 0:
            raise ValueError(
                "AccountDiscoveryCandidate.evidence must be a non-empty list"
                " of EvidencePointer"
            )
        for i, ev in enumerate(self.evidence):
            if not isinstance(ev, EvidencePointer):
                raise ValueError(
                    f"AccountDiscoveryCandidate.evidence[{i}] must be an"
                    " EvidencePointer instance"
                )


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


@dataclass
class AccountDiscoveryResult:
    """
    Normalized result returned by an AccountDiscoveryAdapter.search_accounts().

    candidates may be empty; an empty list signals no_signal to the handler.
    """

    query_object_id: str
    adapter_name: str
    adapter_version: str
    observed_at: str  # ISO 8601
    candidates: list[AccountDiscoveryCandidate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.query_object_id:
            raise ValueError("AccountDiscoveryResult.query_object_id is required")
        if not self.adapter_name:
            raise ValueError("AccountDiscoveryResult.adapter_name is required")
        if not self.adapter_version:
            raise ValueError("AccountDiscoveryResult.adapter_version is required")
        if not self.observed_at:
            raise ValueError("AccountDiscoveryResult.observed_at is required")
        if not isinstance(self.candidates, list):
            raise ValueError("AccountDiscoveryResult.candidates must be a list")
