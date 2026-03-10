"""
Contact enrichment service for Epic G3.

Implements the contact-level enrichment pipeline:
  1. Load Contact from canonical storage.
  2. Find email channel in channels_json.
  3. Validate email (syntax + DNS check, max domain_ok per CONTRACT.yaml).
  4. Update channel validation level (higher level wins — idempotent replay).
  5. Apply send-policy routing rules.
  6. Enqueue copy_generate WorkItem if all preconditions are met.

CONTRACT.yaml epic_g_enrichment_scope.email:
  allowed_automated_ceiling: domain_ok
  forbidden: mailbox probing, provider_verified automation

Routing rules (CONTRACT.yaml routing_rules.copy_generate_preconditions):
  Advance to copy_generate only when:
    - Canonical Contact exists.
    - At least one email channel exists with validation_level >= domain_ok.
    - No STOP-condition from send policy blocks that channel.
    - No role ambiguity that requires human review.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import (
    make_copy_generate_idempotency_key,
    make_work_item_id,
    normalize_email,
)
from aose_worker.services.caps import MAX_PROVIDERS_PER_CONTACT, count_contact_providers
from aose_worker.services.channel_policy import is_send_blocked
from aose_worker.services.email_validator import (
    higher_validation_level,
    validate_email,
    validation_level_gte,
)

# ---------------------------------------------------------------------------
# Allowed role clusters (mirrors CONTRACT.yaml role_model.allowed_clusters)
# ---------------------------------------------------------------------------

_ALLOWED_ROLE_CLUSTERS: frozenset[str] = frozenset(
    {"economic_buyer", "influencer", "gatekeeper", "referrer"}
)

# ---------------------------------------------------------------------------
# Route constants
# ---------------------------------------------------------------------------

ROUTE_COPY_GENERATE = "copy_generate"
ROUTE_POLICY_BLOCKED = "policy_blocked"
ROUTE_NO_SIGNAL = "no_signal"
ROUTE_NEEDS_HUMAN = "needs_human"
ROUTE_BUDGET_EXHAUSTED = "budget_exhausted"  # G4: provider cap hit

# ---------------------------------------------------------------------------
# Service result
# ---------------------------------------------------------------------------


@dataclass
class EnrichmentResult:
    """Summary of a completed contact enrichment service run."""

    contact_id: str
    validation_level_before: str
    validation_level_after: str
    channel_updated: bool
    route: str  # one of the ROUTE_* constants
    copy_generate_enqueued: bool


# ---------------------------------------------------------------------------
# DB read helpers
# ---------------------------------------------------------------------------


def _load_contact(session: Session, contact_id: str) -> dict[str, Any]:
    """Load a Contact row. Raises ValueError if not found."""
    sql = text(
        """
        SELECT contact_id, account_id, full_name,
               channels_json, role_json, status
        FROM contacts
        WHERE contact_id = :id
        """
    )
    row = session.execute(sql, {"id": contact_id}).mappings().first()
    if row is None:
        raise ValueError(f"Contact not found: {contact_id!r}")
    return dict(row)


def _has_linkedin_alias(session: Session, contact_id: str) -> bool:
    """Return True if a linkedin_url_normalized alias exists for this contact."""
    sql = text(
        """
        SELECT 1 FROM contact_aliases
        WHERE contact_id = :id AND alias_type = 'linkedin_url_normalized'
        """
    )
    return session.execute(sql, {"id": contact_id}).first() is not None


def _update_contact_channels(
    session: Session, contact_id: str, channels: list[dict]
) -> None:
    """Persist updated channels_json back to the contact row."""
    session.execute(
        text(
            "UPDATE contacts SET channels_json = CAST(:ch AS JSONB)"
            " WHERE contact_id = :id"
        ),
        {"ch": json.dumps(channels), "id": contact_id},
    )


def _enqueue_copy_generate(
    session: Session,
    contact_id: str,
    account_id: str,
    parent_work_item: dict[str, Any],
) -> bool:
    """
    Enqueue a copy_generate WorkItem (idempotent via ON CONFLICT DO NOTHING).

    Returns True if newly inserted.

    Formula (CONTRACT.yaml idempotency.work_item_keys):
      copy:<contact_id>:v1
    """
    idempotency_key = make_copy_generate_idempotency_key(contact_id)
    work_item_id = make_work_item_id()
    payload = {
        "v": 1,
        "data": {
            "contact_id": contact_id,
            "account_id": account_id,
            "evidence_ids": [],  # populated by later epics
        },
    }

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
            :work_item_id, 'contact', :contact_id, 'copy_generate',
            CAST(:payload AS JSONB), 1,
            :attempt_budget_remaining, :attempt_budget_policy,
            :idempotency_key,
            :trace_run_id, :trace_parent_work_item_id,
            :trace_correlation_id, :trace_policy_pack_id,
            now()
        ) ON CONFLICT (idempotency_key) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "work_item_id": work_item_id,
            "contact_id": contact_id,
            "payload": json.dumps(payload),
            "attempt_budget_remaining": parent_work_item.get(
                "attempt_budget_remaining", 3
            ),
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
        },
    )
    return result.rowcount > 0


# ---------------------------------------------------------------------------
# Role ambiguity helper
# ---------------------------------------------------------------------------


def _is_role_ambiguous(role_json: dict | None) -> bool:
    """
    Return True if the contact's role_cluster is set but not in the allowed set.

    Missing role (None) or missing cluster key is not considered ambiguous.
    """
    if not role_json:
        return False
    cluster = role_json.get("cluster")
    if cluster is None:
        return False
    return cluster not in _ALLOWED_ROLE_CLUSTERS


# ---------------------------------------------------------------------------
# Public service entry point
# ---------------------------------------------------------------------------


def run_contact_enrichment(
    *,
    session: Session,
    contact_id: str,
    parent_work_item: dict[str, Any],
    dns_check: bool = True,
    dns_timeout: float = 5.0,
) -> EnrichmentResult:
    """
    Run contact enrichment for one contact_id.

    Steps:
      1. Load Contact (ValueError if not found → handler parks as contract_error).
      2. Find email channel in channels_json.
      3. Validate email (syntax + DNS up to domain_ok ceiling).
      4. Update channel validation level (higher wins; idempotent replay).
      5. Routing:
           a. No email channel or level < domain_ok        → no_signal
           b. is_send_blocked (free-email / generic mailbox) → policy_blocked
           c. Role ambiguous + no LinkedIn alias            → needs_human
           d. All preconditions met                         → enqueue copy_generate

    Args:
        session:          SQLAlchemy Session (caller manages transactions).
        contact_id:       Canonical contact ID to enrich.
        parent_work_item: Parent WorkItem dict (for trace propagation).
        dns_check:        Set False to skip DNS lookup (unit tests / dry-runs).
        dns_timeout:      DNS lookup timeout in seconds.

    Returns:
        EnrichmentResult describing what happened.

    Raises:
        ValueError:         if Contact not found (caller parks as contract_error).
        TransientDnsError:  if DNS lookup times out (propagates for retry).
    """
    contact = _load_contact(session, contact_id)
    account_id: str = contact["account_id"]

    # --- Provider cap check (G4: max_providers_per_contact) ---
    # Count includes the current WI already in the DB.
    # First enrichment: count=1 < MAX_PROVIDERS_PER_CONTACT → proceeds.
    # Second enrichment (provider 3 total): count=2 >= MAX → parks.
    provider_count = count_contact_providers(session, contact_id)
    if provider_count >= MAX_PROVIDERS_PER_CONTACT:
        return EnrichmentResult(
            contact_id=contact_id,
            validation_level_before="unverified",
            validation_level_after="unverified",
            channel_updated=False,
            route=ROUTE_BUDGET_EXHAUSTED,
            copy_generate_enqueued=False,
        )

    # --- Parse channels_json ---
    channels: list[dict] = contact.get("channels_json") or []
    if not isinstance(channels, list):
        channels = []

    # --- Find email channel ---
    email_channel: dict | None = None
    email_idx: int = -1
    for idx, ch in enumerate(channels):
        if isinstance(ch, dict) and ch.get("type") == "email":
            email_channel = ch
            email_idx = idx
            break

    if email_channel is None:
        return EnrichmentResult(
            contact_id=contact_id,
            validation_level_before="unverified",
            validation_level_after="unverified",
            channel_updated=False,
            route=ROUTE_NO_SIGNAL,
            copy_generate_enqueued=False,
        )

    raw_email: str = email_channel.get("value", "")
    validation_level_before: str = email_channel.get("validated", "unverified")

    # --- Normalize email (should already be normalized; re-normalize for safety) ---
    norm_email = normalize_email(raw_email) or raw_email

    # --- Validate email (TransientDnsError propagates for RQ retry) ---
    new_level = validate_email(
        norm_email,
        dns_check=dns_check,
        dns_timeout=dns_timeout,
    )

    # Higher validation level wins (idempotent: replay produces same or higher level)
    effective_level = higher_validation_level(validation_level_before, new_level)

    # --- Update channel validation state ---
    channels[email_idx] = {
        **email_channel,
        "validated": effective_level,
        "validated_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    _update_contact_channels(session, contact_id, channels)
    channel_updated = effective_level != validation_level_before

    validation_level_after = effective_level

    # --- Routing rule 1: must reach domain_ok to advance ---
    if not validation_level_gte(validation_level_after, "domain_ok"):
        return EnrichmentResult(
            contact_id=contact_id,
            validation_level_before=validation_level_before,
            validation_level_after=validation_level_after,
            channel_updated=channel_updated,
            route=ROUTE_NO_SIGNAL,
            copy_generate_enqueued=False,
        )

    # --- Routing rule 2: send-policy block (free-email / generic mailbox) ---
    if is_send_blocked(norm_email):
        return EnrichmentResult(
            contact_id=contact_id,
            validation_level_before=validation_level_before,
            validation_level_after=validation_level_after,
            channel_updated=channel_updated,
            route=ROUTE_POLICY_BLOCKED,
            copy_generate_enqueued=False,
        )

    # --- Routing rule 3: role ambiguity without LinkedIn anchor ---
    role_json: dict | None = contact.get("role_json") or None
    if _is_role_ambiguous(role_json) and not _has_linkedin_alias(session, contact_id):
        return EnrichmentResult(
            contact_id=contact_id,
            validation_level_before=validation_level_before,
            validation_level_after=validation_level_after,
            channel_updated=channel_updated,
            route=ROUTE_NEEDS_HUMAN,
            copy_generate_enqueued=False,
        )

    # --- All preconditions met: enqueue copy_generate ---
    enqueued = _enqueue_copy_generate(session, contact_id, account_id, parent_work_item)
    return EnrichmentResult(
        contact_id=contact_id,
        validation_level_before=validation_level_before,
        validation_level_after=validation_level_after,
        channel_updated=channel_updated,
        route=ROUTE_COPY_GENERATE,
        copy_generate_enqueued=enqueued,
    )
