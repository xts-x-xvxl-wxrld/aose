"""
Approval decision service for the AOSE worker pipeline.

Provides authority checking, routing, and idempotent persistence for
ApprovalDecision records.

Implements the authority rules and routing table from SPEC-H3 and CONTRACT.yaml
approval_workflow section.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text

# Canonical action type for the approval_request stage (narrowest conservative value)
ACTION_TYPE_DEFAULT = "approve_send"

# Roles that may record decisions (CONTRACT.yaml authority_rules)
_ALLOWED_REVIEWER_ROLES = frozenset({"operator", "admin"})

# Routing: decision status → next pipeline stage (CONTRACT.yaml routing_rules)
ROUTING: dict[str, str] = {
    "approved": "sending_dispatch",
    "rejected": "parked:rejected",
    "needs_rewrite": "parked:needs_rewrite",
    "needs_more_evidence": "parked:needs_more_evidence",
}

# Canonical decision statuses (CONTRACT.yaml decision_statuses)
DECISION_STATUSES = frozenset(
    {"approved", "rejected", "needs_rewrite", "needs_more_evidence"}
)


class AuthorityError(Exception):
    """Reviewer lacks authority to record a decision."""


class InvalidStatusError(Exception):
    """Decision status is not in the locked enum."""


def check_authority(reviewer_role: str) -> None:
    """Raise AuthorityError if reviewer_role may not record a decision."""
    if reviewer_role not in _ALLOWED_REVIEWER_ROLES:
        raise AuthorityError(
            f"reviewer_role {reviewer_role!r} may not record a decision. "
            f"Allowed: {sorted(_ALLOWED_REVIEWER_ROLES)}"
        )


def check_status(status: str) -> None:
    """Raise InvalidStatusError if status is not in the locked decision status set."""
    if status not in DECISION_STATUSES:
        raise InvalidStatusError(
            f"Invalid decision status: {status!r}. "
            f"Allowed: {sorted(DECISION_STATUSES)}"
        )


def get_next_stage(status: str) -> str:
    """Return next pipeline stage for a given (valid) decision status."""
    return ROUTING[status]


def lookup_decision_by_key(session: Any, decision_key: str) -> str | None:
    """Return existing decision_id for decision_key, or None if absent."""
    sql = text(
        "SELECT decision_id FROM approval_decisions WHERE decision_key = :dk LIMIT 1"
    )
    row = session.execute(sql, {"dk": decision_key}).first()
    return row[0] if row else None


def persist_decision(
    session: Any,
    *,
    decision_id: str,
    decision_key: str,
    draft_id: str,
    work_item_id: str,
    contact_id: str,
    action_type: str,
    status: str,
    reviewer_id: str,
    reviewer_role: str,
    policy_pack_id: str,
    notes: str | None,
    overridden_gates: list,
) -> bool:
    """
    Insert ApprovalDecision. Returns True if newly inserted, False on replay.

    ON CONFLICT on decision_key → DO NOTHING (replay-safe).
    Commit must be called by the caller after this returns.
    """
    sql = text(
        """
        INSERT INTO approval_decisions (
            decision_id, decision_key, draft_id, work_item_id, contact_id,
            action_type, status, reviewer_id, reviewer_role,
            notes, overridden_gates_json, policy_pack_id, decided_at, created_at, v
        ) VALUES (
            :decision_id, :decision_key, :draft_id, :work_item_id, :contact_id,
            :action_type, :status, :reviewer_id, :reviewer_role,
            :notes, CAST(:overridden_gates AS JSONB), :policy_pack_id, :decided_at, now(), 1
        ) ON CONFLICT (decision_key) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "decision_id": decision_id,
            "decision_key": decision_key,
            "draft_id": draft_id,
            "work_item_id": work_item_id,
            "contact_id": contact_id,
            "action_type": action_type,
            "status": status,
            "reviewer_id": reviewer_id,
            "reviewer_role": reviewer_role,
            "notes": notes,
            "overridden_gates": json.dumps(overridden_gates),
            "policy_pack_id": policy_pack_id,
            "decided_at": datetime.now(tz=timezone.utc),
        },
    )
    return result.rowcount > 0
