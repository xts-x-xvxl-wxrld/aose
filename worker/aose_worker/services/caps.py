"""
Deterministic cap enforcement helpers for Epic G4.

Implements CONTRACT.yaml caps (inherited from policy_pack safe_v0_1):
  max_contacts_total_per_run:      60
  max_contacts_per_account:         3
  max_enrich_attempts_per_contact:  2
  max_providers_per_contact:        2
  max_drafts_per_contact:           2

These caps are authoritative and must not be bypassed by any code path
(people_search, contact_enrichment, manual CSV import, or adapter mode).

Deterministic sort order for candidate selection
(CONTRACT.yaml caps.enforcement_rules.contacts_per_account):
  1. Higher confidence (descending; None → -1.0)
  2. Higher role_confidence (descending; None → -1.0)
  3. Candidate with normalized email preferred over LinkedIn-only (True first)
  4. Lexicographic tie-break on contact_id (ascending)

This ordering is stable and replay-safe: replaying the same set of candidates
always produces the same set of survivors.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import normalize_email

# ---------------------------------------------------------------------------
# Authoritative cap constants (CONTRACT.yaml caps.inherited_from_policy_pack)
# ---------------------------------------------------------------------------

MAX_CONTACTS_TOTAL_PER_RUN: int = 60
MAX_CONTACTS_PER_ACCOUNT: int = 3
MAX_ENRICH_ATTEMPTS_PER_CONTACT: int = 2
MAX_PROVIDERS_PER_CONTACT: int = 2
MAX_DRAFTS_PER_CONTACT: int = 2


# ---------------------------------------------------------------------------
# Deterministic candidate sort key
# ---------------------------------------------------------------------------


def candidate_sort_key(candidate: Any, contact_id: str) -> tuple:
    """
    Return a deterministic sort key for a ContactCandidate.

    Sort order (ascending by key):
      1. Higher confidence first  (negate for descending; None → -1.0)
      2. Higher role_confidence first (negate for descending; None → -1.0)
      3. Email-bearing candidate first (negate has_email for True-first)
      4. Lexicographic contact_id ascending (tie-break)

    Args:
        candidate:  ContactCandidate (duck-typed: needs .confidence,
                    .role_confidence, .email attributes).
        contact_id: Precomputed canonical contact_id for this candidate.
    """
    conf = candidate.confidence if candidate.confidence is not None else -1.0
    role_conf = (
        candidate.role_confidence if candidate.role_confidence is not None else -1.0
    )
    has_email = 1 if normalize_email(candidate.email) is not None else 0
    return (-conf, -role_conf, -has_email, contact_id)


# ---------------------------------------------------------------------------
# Run-level contact accounting
# ---------------------------------------------------------------------------


def count_run_contacts(session: Session, run_id: str) -> int:
    """
    Count contact_enrichment WorkItems enqueued under the given run_id.

    This is the canonical proxy for "contacts created in this run," because
    exactly one contact_enrichment WorkItem is enqueued per surviving contact
    (idempotent via ON CONFLICT DO NOTHING on idempotency_key).

    Args:
        session: SQLAlchemy Session.
        run_id:  trace_run_id of the current pipeline run.

    Returns:
        Number of contact_enrichment WorkItems with trace_run_id == run_id.
    """
    sql = text(
        """
        SELECT COUNT(*) FROM work_items
        WHERE stage = 'contact_enrichment'
          AND trace_run_id = :run_id
        """
    )
    return session.execute(sql, {"run_id": run_id}).scalar() or 0


# ---------------------------------------------------------------------------
# Per-contact provider accounting
# ---------------------------------------------------------------------------


def count_contact_providers(session: Session, contact_id: str) -> int:
    """
    Count the number of contact_enrichment WorkItems referencing this contact.

    Each WorkItem represents one provider enrichment attempt. The people_search
    adapter counts as provider 1 (implicit in contact creation); enrichment
    WIs count as providers 2+. Once count >= MAX_PROVIDERS_PER_CONTACT,
    further enrichment is refused and parked as budget_exhausted.

    Args:
        session:    SQLAlchemy Session.
        contact_id: Canonical contact_id to check.

    Returns:
        Count of contact_enrichment WorkItems for this contact.
    """
    sql = text(
        """
        SELECT COUNT(*) FROM work_items
        WHERE entity_ref_id = :contact_id
          AND stage = 'contact_enrichment'
        """
    )
    return session.execute(sql, {"contact_id": contact_id}).scalar() or 0
