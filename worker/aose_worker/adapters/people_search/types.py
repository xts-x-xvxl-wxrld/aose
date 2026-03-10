"""
Typed shapes for the PeopleSearch adapter interface.

All shapes enforce the Epic G adapter contract at construction time.
Normalization (email, LinkedIn URL, confidence clamping) must be applied
at the adapter boundary before constructing these objects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aose_worker.canonical_ids import normalize_email, normalize_linkedin_url

# ---------------------------------------------------------------------------
# Allowed role clusters (CONTRACT.yaml role_model.allowed_clusters)
# ---------------------------------------------------------------------------

ALLOWED_ROLE_CLUSTERS: frozenset[str] = frozenset(
    {"economic_buyer", "influencer", "gatekeeper", "referrer"}
)


# ---------------------------------------------------------------------------
# Candidate shape
# ---------------------------------------------------------------------------


@dataclass
class ContactCandidate:
    """
    Normalized candidate returned by a PeopleSearchAdapter.

    Required fields enforce the Epic G adapter contract.
    At least one of email or linkedin_url must be non-None.
    Normalization invariants that must hold at construction:
    - email must already be in normalized form (lowercase local + normalized domain)
    - linkedin_url must already be in normalized form (no query/fragment, lowercase)
    - confidence (if provided) must already be clamped to [0.0, 1.0]
    - provenance must carry source_provider, source_ref, observed_at
    """

    # Required fields
    account_id: str
    full_name: str
    provenance: dict[str, Any]

    # At least one identity field required
    email: str | None = None
    linkedin_url: str | None = None

    # Optional fields
    role_title: str | None = None
    role_cluster: str | None = None
    role_confidence: float | None = None
    source_provider: str | None = None
    source_ref: str | None = None
    observed_at: str | None = None
    confidence: float | None = None

    def __post_init__(self) -> None:
        if not self.account_id:
            raise ValueError("ContactCandidate.account_id is required")
        if not self.full_name:
            raise ValueError("ContactCandidate.full_name is required")
        if not isinstance(self.provenance, dict):
            raise ValueError("ContactCandidate.provenance must be a dict")
        for prov_field in ("source_provider", "source_ref", "observed_at"):
            if not self.provenance.get(prov_field):
                raise ValueError(
                    f"ContactCandidate.provenance must contain '{prov_field}'"
                )

        # At least one identity field
        norm_email = normalize_email(self.email)
        norm_li = normalize_linkedin_url(self.linkedin_url)
        if norm_email is None and norm_li is None:
            raise ValueError(
                "ContactCandidate requires at least one valid identity field"
                " (email or linkedin_url)"
            )

        # Confidence must be in range if provided
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"ContactCandidate.confidence must be in [0.0, 1.0],"
                f" got {self.confidence}"
            )

        # role_confidence must be in range if provided
        if self.role_confidence is not None and not (
            0.0 <= self.role_confidence <= 1.0
        ):
            raise ValueError(
                f"ContactCandidate.role_confidence must be in [0.0, 1.0],"
                f" got {self.role_confidence}"
            )

        # role_cluster must be from the locked set if provided
        if (
            self.role_cluster is not None
            and self.role_cluster not in ALLOWED_ROLE_CLUSTERS
        ):
            raise ValueError(
                f"ContactCandidate.role_cluster must be one of"
                f" {sorted(ALLOWED_ROLE_CLUSTERS)}, got {self.role_cluster!r}"
            )
