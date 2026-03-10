"""
People search service for Epic G1, with G4 cap enforcement.

Implements the core people search logic:
  1. Load Account from canonical storage (raises ValueError if not found).
  2. Check run-level contact cap (max_contacts_total_per_run).
  3. Call the configured adapter.
  4. Validate and normalize each candidate.
  5. Dedup by contact_id within this run.
  6. Sort by deterministic priority order (G4 enforcement).
  7. Write canonical Contact and ContactAlias records (idempotent).
  8. Enqueue downstream contact_enrichment WorkItems.

Rules:
- Uses text() SQL to avoid importing aose_api ORM models into the worker.
- All writes are idempotent via ON CONFLICT DO NOTHING.
- Does NOT write Scorecard, OutreachDraft, ApprovalDecision, SendAttempt.
- Budget decrement is the caller's (handler's) responsibility.
- Structured event emission is the caller's (handler's) responsibility.
- CAST() syntax used for explicit type casts to avoid SQLAlchemy text() parser
  conflicts with PostgreSQL's :: operator when adjacent to named parameters.

Cap enforcement (CONTRACT.yaml caps, G4):
- max_contacts_per_account: kept via per-account count + deterministic sort.
- max_contacts_total_per_run: checked via count_run_contacts before writing.
- Enrichment budget set to MAX_ENRICH_ATTEMPTS_PER_CONTACT (not inherited).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from aose_worker.adapters.people_search.base import PeopleSearchAdapter
from aose_worker.adapters.people_search.types import (
    ALLOWED_ROLE_CLUSTERS,
    ContactCandidate,
)
from aose_worker.canonical_ids import (
    make_contact_id,
    make_enrichment_idempotency_key,
    make_work_item_id,
    normalize_email,
    normalize_linkedin_url,
)
from aose_worker.services.caps import (
    MAX_CONTACTS_PER_ACCOUNT,
    MAX_CONTACTS_TOTAL_PER_RUN,
    MAX_ENRICH_ATTEMPTS_PER_CONTACT,
    candidate_sort_key,
    count_run_contacts,
)

# ---------------------------------------------------------------------------
# Service result
# ---------------------------------------------------------------------------


@dataclass
class PeopleSearchServiceResult:
    """Summary of a completed people search service run."""

    contacts_created: int = 0
    contacts_skipped: int = 0  # already existed or cap-rejected (idempotent replay)
    contacts_rejected: int = 0  # failed validation
    downstream_enqueued: int = 0
    no_signal: bool = False
    needs_human: bool = False
    run_cap_exhausted: bool = False  # G4: run-level cap hit
    contact_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DB read helpers
# ---------------------------------------------------------------------------


def _load_account(session: Session, account_id: str) -> dict[str, Any]:
    """Load an Account row by primary key. Raises ValueError if not found."""
    sql = text(
        """
        SELECT account_id, name, domain, country, status
        FROM accounts
        WHERE account_id = :id
        """
    )
    row = session.execute(sql, {"id": account_id}).mappings().first()
    if row is None:
        raise ValueError(f"Account not found: {account_id!r}")
    return dict(row)


def _count_existing_contacts(session: Session, account_id: str) -> int:
    """Return the number of Contact rows already stored for this account."""
    sql = text("SELECT COUNT(*) FROM contacts WHERE account_id = :account_id")
    return session.execute(sql, {"account_id": account_id}).scalar() or 0


# ---------------------------------------------------------------------------
# Canonical write helpers
# ---------------------------------------------------------------------------


def _write_contact(
    session: Session,
    contact_id: str,
    candidate: ContactCandidate,
    norm_email: str | None,
    norm_li: str | None,
    now: datetime,
) -> bool:
    """
    Insert Contact row (idempotent via ON CONFLICT DO NOTHING on PK).

    Returns True if a new row was inserted, False if it already existed.
    Status is always 'candidate' after discovery.
    """
    channels: list[dict] = []
    source_trace = {
        "source_provider": candidate.source_provider
        or candidate.provenance.get("source_provider", ""),
        "source_ref": candidate.source_ref
        or candidate.provenance.get("source_ref", ""),
        "observed_at": candidate.observed_at
        or candidate.provenance.get("observed_at", ""),
        "confidence": candidate.confidence,
    }

    if norm_email:
        channels.append(
            {
                "type": "email",
                "value": norm_email,
                "validated": "unverified",
                "validated_at": None,
                "source_trace": source_trace,
            }
        )

    role_json: dict | None = None
    if candidate.role_title or candidate.role_cluster:
        role_json = {
            "title": candidate.role_title,
            "cluster": candidate.role_cluster,
            "confidence": candidate.role_confidence,
        }

    sql = text(
        """
        INSERT INTO contacts (
            contact_id, account_id, full_name,
            role_json, channels_json, provenance_json,
            status, v
        ) VALUES (
            :contact_id, :account_id, :full_name,
            CAST(:role_json AS JSONB), CAST(:channels_json AS JSONB),
            CAST(:provenance_json AS JSONB),
            'candidate', 1
        ) ON CONFLICT (contact_id) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "contact_id": contact_id,
            "account_id": candidate.account_id,
            "full_name": candidate.full_name,
            "role_json": json.dumps(role_json),
            "channels_json": json.dumps(channels),
            "provenance_json": json.dumps(candidate.provenance),
        },
    )
    return result.rowcount > 0


def _write_contact_alias(
    session: Session,
    contact_id: str,
    account_id: str,
    alias_type: str,
    alias_value: str,
) -> None:
    """
    Insert ContactAlias row (idempotent via ON CONFLICT DO NOTHING on PK
    (contact_id, alias_type) and unique constraint on account_id+type+value).
    """
    sql = text(
        """
        INSERT INTO contact_aliases (
            contact_id, account_id, alias_type, alias_value, v
        ) VALUES (
            :contact_id, :account_id, :alias_type, :alias_value, 1
        ) ON CONFLICT (contact_id, alias_type) DO NOTHING
        """
    )
    session.execute(
        sql,
        {
            "contact_id": contact_id,
            "account_id": account_id,
            "alias_type": alias_type,
            "alias_value": alias_value,
        },
    )


def _write_aliases(
    session: Session,
    contact_id: str,
    account_id: str,
    norm_email: str | None,
    norm_li: str | None,
) -> None:
    """
    Write ContactAlias rows for normalized identities.

    CONTRACT.yaml contact_identity.alias_types:
    - email_normalized (when normalized email present)
    - linkedin_url_normalized (when normalized LinkedIn URL present)
    """
    if norm_email:
        _write_contact_alias(
            session, contact_id, account_id, "email_normalized", norm_email
        )
    if norm_li:
        _write_contact_alias(
            session, contact_id, account_id, "linkedin_url_normalized", norm_li
        )


def _enqueue_enrichment_work_item(
    session: Session,
    contact_id: str,
    parent_work_item: dict[str, Any],
    now: datetime,
) -> bool:
    """
    Enqueue a downstream contact_enrichment WorkItem (idempotent via
    ON CONFLICT DO NOTHING on idempotency_key unique constraint).

    Returns True if the work item was newly inserted.

    Budget is set to MAX_ENRICH_ATTEMPTS_PER_CONTACT (G4 enforcement),
    not inherited from the parent, so enrichment always starts with the
    correct per-contact attempt cap.
    """
    idempotency_key = make_enrichment_idempotency_key(contact_id)
    work_item_id = make_work_item_id()
    payload = {"v": 1, "data": {"contact_id": contact_id}}

    sql = text(
        """
        INSERT INTO work_items (
            work_item_id, entity_ref_type, entity_ref_id, stage,
            payload_json, payload_version,
            attempt_budget_remaining, attempt_budget_policy,
            idempotency_key,
            trace_run_id, trace_parent_work_item_id,
            trace_correlation_id, trace_policy_pack_id,
            created_at
        ) VALUES (
            :work_item_id, 'contact', :contact_id, 'contact_enrichment',
            CAST(:payload AS JSONB), 1,
            :attempt_budget_remaining, :attempt_budget_policy,
            :idempotency_key,
            :trace_run_id, :trace_parent_work_item_id,
            :trace_correlation_id, :trace_policy_pack_id,
            :created_at
        ) ON CONFLICT (idempotency_key) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "work_item_id": work_item_id,
            "contact_id": contact_id,
            "payload": json.dumps(payload),
            # G4: enrichment budget is always MAX_ENRICH_ATTEMPTS_PER_CONTACT,
            # not inherited from parent (which may have a different policy).
            "attempt_budget_remaining": MAX_ENRICH_ATTEMPTS_PER_CONTACT,
            "attempt_budget_policy": parent_work_item.get(
                "attempt_budget_policy", "standard"
            ),
            "idempotency_key": idempotency_key,
            "trace_run_id": parent_work_item.get("trace_run_id", ""),
            "trace_parent_work_item_id": parent_work_item.get("work_item_id"),
            "trace_correlation_id": parent_work_item.get("trace_correlation_id", ""),
            "trace_policy_pack_id": parent_work_item.get(
                "trace_policy_pack_id", "safe_v0_1"
            ),
            "created_at": now,
        },
    )
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Role ambiguity check
# ---------------------------------------------------------------------------


def _is_role_ambiguous(candidate: ContactCandidate) -> bool:
    """
    Return True if the role is ambiguous.

    Ambiguous means role_cluster is not in the allowed set.
    A candidate with no role at all is not ambiguous.
    """
    if (
        candidate.role_cluster is not None
        and candidate.role_cluster not in ALLOWED_ROLE_CLUSTERS
    ):
        return True
    return False


# ---------------------------------------------------------------------------
# Public service entry point
# ---------------------------------------------------------------------------


def run_people_search(
    *,
    session: Session,
    account_id: str,
    adapter: PeopleSearchAdapter,
    role_targets: list[str] | None,
    limits: dict[str, Any],
    context: dict[str, Any],
    parent_work_item: dict[str, Any],
) -> PeopleSearchServiceResult:
    """
    Run people search for one account_id.

    Args:
        session:          SQLAlchemy Session (caller manages transaction).
        account_id:       Canonical account ID to search within.
        adapter:          PeopleSearchAdapter implementation to use.
        role_targets:     Optional list of role clusters to target.
        limits:           Run caps dict (max_contacts_per_account, etc.).
        context:          Caller context (policy_pack_id, run_id, trace fields).
        parent_work_item: Dict of the parent WorkItem row (for trace propagation).

    Returns:
        PeopleSearchServiceResult summarising what was written.

    Raises:
        ValueError: if Account is not found (contract error).
    """
    max_contacts = int(limits.get("max_contacts_per_account", MAX_CONTACTS_PER_ACCOUNT))
    svc_result = PeopleSearchServiceResult()

    # 1. Verify account exists
    _load_account(session, account_id)

    # 2. Run-level cap check (G4: max_contacts_total_per_run)
    run_id = parent_work_item.get("trace_run_id", "")
    run_count = 0
    if run_id:
        run_count = count_run_contacts(session, run_id)
        if run_count >= MAX_CONTACTS_TOTAL_PER_RUN:
            svc_result.run_cap_exhausted = True
            svc_result.no_signal = True
            return svc_result

    # 3. Call adapter
    candidates = adapter.search_people(account_id, role_targets)

    # 4. Validate, normalize, dedup — produce pre-processed tuples
    #    Each tuple: (candidate, norm_email, norm_li, contact_id)
    now = datetime.now(tz=timezone.utc)
    pre_candidates: list[tuple] = []
    seen_contact_ids: set[str] = set()

    for candidate in candidates:
        # Validate account_id matches
        if candidate.account_id != account_id:
            svc_result.contacts_rejected += 1
            continue

        # Normalize identities
        norm_email = normalize_email(candidate.email)
        norm_li = normalize_linkedin_url(candidate.linkedin_url)

        # Compute contact_id (rejects if neither identity computable)
        contact_id = make_contact_id(account_id, norm_email, norm_li)
        if contact_id is None:
            svc_result.contacts_rejected += 1
            continue

        # Role ambiguity check: ambiguous role + no LinkedIn → needs_human
        if _is_role_ambiguous(candidate) and norm_li is None:
            svc_result.needs_human = True
            svc_result.contacts_rejected += 1
            continue

        # Dedup within this run
        if contact_id in seen_contact_ids:
            svc_result.contacts_skipped += 1
            continue
        seen_contact_ids.add(contact_id)

        pre_candidates.append((candidate, norm_email, norm_li, contact_id))

    # 5. Sort deterministically (G4: highest-confidence survivors selected first)
    pre_candidates.sort(key=lambda t: candidate_sort_key(t[0], t[3]))

    # 6. Apply per-account cap + run-level cap, then persist
    existing_count = _count_existing_contacts(session, account_id)
    run_remaining = MAX_CONTACTS_TOTAL_PER_RUN - run_count
    new_count = 0

    for candidate, norm_email, norm_li, contact_id in pre_candidates:
        # Per-account cap
        if existing_count + new_count >= max_contacts:
            svc_result.contacts_skipped += 1
            continue

        # Run-level cap (across accounts in this run)
        if new_count >= run_remaining:
            svc_result.run_cap_exhausted = True
            svc_result.contacts_skipped += 1
            continue

        # Write Contact row
        newly_created = _write_contact(
            session, contact_id, candidate, norm_email, norm_li, now
        )
        if newly_created:
            svc_result.contacts_created += 1
            svc_result.contact_ids.append(contact_id)
            new_count += 1
        else:
            svc_result.contacts_skipped += 1

        # Write aliases for all surviving contacts (idempotent)
        _write_aliases(session, contact_id, account_id, norm_email, norm_li)

        # Enqueue downstream contact_enrichment work item
        enqueued = _enqueue_enrichment_work_item(
            session, contact_id, parent_work_item, now
        )
        if enqueued:
            svc_result.downstream_enqueued += 1

    # no_signal: no candidates passed validation and no contacts survived
    total_surviving = svc_result.contacts_created + svc_result.contacts_skipped
    if len(candidates) == 0 or total_surviving == 0:
        svc_result.no_signal = True

    return svc_result
