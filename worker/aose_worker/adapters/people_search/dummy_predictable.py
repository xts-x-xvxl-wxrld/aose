"""
Dummy predictable adapter for Epic G people search.

Satisfies SPEC-G1 acceptance checks:
- No network access required.
- Deterministic output for the same account_id input.
- Stable provenance fields.
- Tests are independent of external provider availability.

Placeholder reference: PH-EPIC-G-001 — real adapter selection is deferred.
"""

from __future__ import annotations

import hashlib

from aose_worker.canonical_ids import normalize_email, normalize_linkedin_url

from .base import PeopleSearchAdapter
from .types import ContactCandidate

_ADAPTER_NAME = "dummy_predictable_people"

# Fixed timestamp for deterministic test output.
_FIXED_OBSERVED_AT = "2026-01-01T00:00:00Z"

# Candidate templates — slot is stable; same slot always produces identical output.
_CANDIDATE_TEMPLATES = [
    {
        "full_name": "Alice Smith",
        "email": "alice.smith@{domain}",
        "linkedin_url": None,
        "role_title": "Chief Executive Officer",
        "role_cluster": "economic_buyer",
        "role_confidence": 0.90,
        "confidence": 0.85,
    },
    {
        "full_name": "Bob Jones",
        "email": None,
        "linkedin_url": "https://www.linkedin.com/in/bob-jones-{slug}",
        "role_title": "Head of Engineering",
        "role_cluster": "influencer",
        "role_confidence": 0.75,
        "confidence": 0.70,
    },
]


def _make_slug(account_id: str, slot: int) -> str:
    """Return a short deterministic slug for dummy candidate URLs."""
    raw = f"dummy_people|{account_id}|{slot}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _extract_domain_from_account_id(account_id: str) -> str:
    """
    Derive a dummy domain string from account_id for predictable email generation.

    If account_id looks like 'account:<domain>', extract domain; otherwise
    use a stable fallback.
    """
    parts = account_id.split(":", 1)
    if len(parts) == 2 and "." in parts[1]:
        return parts[1]
    slug = hashlib.sha256(account_id.encode("utf-8")).hexdigest()[:8]
    return f"dummy-{slug}.example.com"


class DummyPredictablePeopleAdapter(PeopleSearchAdapter):
    """
    Deterministic test adapter for people search. No network access.

    Returns a fixed set of normalized candidates derived from the account_id.
    Two calls with identical inputs always produce structurally identical output.

    Placeholder: PH-EPIC-G-001 (real adapter selection deferred).
    """

    @property
    def adapter_name(self) -> str:
        return _ADAPTER_NAME

    def search_people(
        self,
        account_id: str,
        role_targets: list[str] | None = None,
    ) -> list[ContactCandidate]:
        domain = _extract_domain_from_account_id(account_id)
        candidates: list[ContactCandidate] = []

        for slot, template in enumerate(_CANDIDATE_TEMPLATES):
            slug = _make_slug(account_id, slot)
            source_ref = slug

            raw_email = template["email"]
            raw_li = template["linkedin_url"]

            if raw_email is not None:
                raw_email = raw_email.format(domain=domain)
            if raw_li is not None:
                raw_li = raw_li.format(slug=slug)

            norm_email = normalize_email(raw_email)
            norm_li = normalize_linkedin_url(raw_li)

            # Skip if neither identity normalizes (should not happen with templates)
            if norm_email is None and norm_li is None:
                continue

            provenance: dict = {
                "source_provider": _ADAPTER_NAME,
                "source_ref": source_ref,
                "observed_at": _FIXED_OBSERVED_AT,
                "slot": slot,
            }

            candidates.append(
                ContactCandidate(
                    account_id=account_id,
                    full_name=template["full_name"],
                    provenance=provenance,
                    email=norm_email,
                    linkedin_url=norm_li,
                    role_title=template.get("role_title"),
                    role_cluster=template.get("role_cluster"),
                    role_confidence=template.get("role_confidence"),
                    source_provider=_ADAPTER_NAME,
                    source_ref=source_ref,
                    observed_at=_FIXED_OBSERVED_AT,
                    confidence=template.get("confidence"),
                )
            )

        return candidates
