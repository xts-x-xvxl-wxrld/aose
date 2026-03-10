"""
Structured event writer for the AOSE worker pipeline.

Implements CONTRACT.yaml structured_events rules:
  - every handler emits handler_started + exactly one terminal outcome event
  - event_type must be one of the canonical structured_event_types
  - outcome must be one of the canonical structured_event_outcomes
  - error_code must be null or one of the canonical error_codes
  - counters must contain numeric-only machine metrics
  - refs must contain only safe machine references (no PII)
  - structured event writes must not decrement the attempt budget

Redaction policy (CONTRACT.yaml redaction_and_security):
  Never include in events:
    - full email addresses
    - full phone numbers
    - full message bodies
    - raw provider secrets or credentials

  Allowed in refs:
    - canonical IDs
    - contact_id, evidence_ids, template_id
    - claim_hashes, safe hashes, domain fragments
    - provider identifiers

This module is the single shared event writer for all handlers.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ── Canonical enums (CONTRACT.yaml canonical_enums) ──────────────────────────

CANONICAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "handler_started",
        "handler_succeeded",
        "handler_parked",
        "handler_failed_contract",
        "handler_failed_transient",
        "handler_noop_idempotent",
        "budget_decremented",
        "retry_scheduled",
        "work_item_completed",
        "work_item_parked",
        "work_item_failed_contract",
        "work_item_failed_transient",
        # Epic H event kinds (CONTRACT.yaml structured_events.required_event_kinds)
        "evidence_digest_built",
        "draft_generated",
        "draft_flagged_for_review",
        "approval_recorded",
    }
)

CANONICAL_OUTCOMES: frozenset[str] = frozenset(
    {
        "ok",
        "parked",
        "failed_contract",
        "failed_transient",
        "retry_scheduled",
        "noop",
    }
)

CANONICAL_ERROR_CODES: frozenset[str] = frozenset(
    {
        "contract_error",
        "transient_error",
        "budget_exhausted",
        "no_signal",
        "policy_blocked",
        "needs_human",
    }
)

TERMINAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "work_item_completed",
        "work_item_parked",
        "work_item_failed_contract",
        "work_item_failed_transient",
    }
)

# ── Redaction patterns (CONTRACT.yaml redaction_and_security) ─────────────────
# These patterns detect PII that must never appear in structured events.

# Full email: local@domain — local contains no whitespace, domain has a dot
_RE_FULL_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# E.164 phone and common US formats (conservative — matches clear phone strings)
_RE_FULL_PHONE = re.compile(
    r"(?<!\w)(\+?1[\s\-.]?)?\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\w)"
)

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("full_email_address", _RE_FULL_EMAIL),
    ("full_phone_number", _RE_FULL_PHONE),
]


# ── Event data ────────────────────────────────────────────────────────────────


@dataclass
class StructuredEventData:
    """
    All required fields for one structured event (CONTRACT.yaml structured_events).

    entity_ref is represented as (entity_ref_type, entity_ref_id) matching the
    flattened column layout of work_items and structured_events tables.
    """

    module: str
    work_item_id: str
    entity_ref_type: str
    entity_ref_id: str
    stage: str
    event_type: str
    outcome: str
    counters: dict[str, int | float]
    refs: dict[str, Any]
    error_code: str | None = None
    v: int = 1
    event_id: str = field(default_factory=lambda: f"evt:{uuid.uuid4().hex}")
    occurred_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


# ── Validation ────────────────────────────────────────────────────────────────


def validate_event(event: StructuredEventData) -> None:
    """
    Validate all fields of a StructuredEventData against the contract.

    Raises ValueError with a descriptive message on any violation.
    Must be called before persisting any event.
    """
    if event.event_type not in CANONICAL_EVENT_TYPES:
        raise ValueError(
            f"Invalid event_type {event.event_type!r}. "
            f"Must be one of: {sorted(CANONICAL_EVENT_TYPES)}"
        )

    if event.outcome not in CANONICAL_OUTCOMES:
        raise ValueError(
            f"Invalid outcome {event.outcome!r}. "
            f"Must be one of: {sorted(CANONICAL_OUTCOMES)}"
        )

    if event.error_code is not None and event.error_code not in CANONICAL_ERROR_CODES:
        raise ValueError(
            f"Invalid error_code {event.error_code!r}. "
            f"Must be null or one of: {sorted(CANONICAL_ERROR_CODES)}"
        )

    _validate_counters(event.counters)
    _validate_refs_redacted(event.refs)

    if not event.module:
        raise ValueError("module must not be empty")
    if not event.work_item_id:
        raise ValueError("work_item_id must not be empty")
    if not event.stage:
        raise ValueError("stage must not be empty")
    if not event.entity_ref_type or not event.entity_ref_id:
        raise ValueError("entity_ref_type and entity_ref_id must not be empty")


def _validate_counters(counters: dict[str, Any]) -> None:
    """Counters must contain only numeric (int or float) values."""
    if not isinstance(counters, dict):
        raise ValueError("counters must be a dict")
    for k, v in counters.items():
        if not isinstance(v, (int, float)):
            raise ValueError(
                f"counters[{k!r}] must be numeric (int or float), got {type(v).__name__!r}"
            )


def _validate_refs_redacted(refs: dict[str, Any]) -> None:
    """
    Scan refs for PII patterns that must never appear in structured events.

    Raises ValueError naming the detected PII category if any match is found.
    """
    if not isinstance(refs, dict):
        raise ValueError("refs must be a dict")
    # Collect all string values in refs (shallow scan of top-level values)
    string_values: list[str] = []
    for v in refs.values():
        if isinstance(v, str):
            string_values.append(v)
        elif isinstance(v, list):
            string_values.extend(item for item in v if isinstance(item, str))

    for label, pattern in _PII_PATTERNS:
        for s in string_values:
            if pattern.search(s):
                raise ValueError(
                    f"refs contains {label} which must not appear in structured events. "
                    "Redact before emitting."
                )


# ── Convenience builders ──────────────────────────────────────────────────────


def build_event(
    *,
    module: str,
    work_item_id: str,
    entity_ref_type: str,
    entity_ref_id: str,
    stage: str,
    event_type: str,
    outcome: str,
    error_code: str | None = None,
    counters: dict[str, int | float] | None = None,
    refs: dict[str, Any] | None = None,
) -> StructuredEventData:
    """Build and validate a StructuredEventData. Raises ValueError on invalid input."""
    event = StructuredEventData(
        module=module,
        work_item_id=work_item_id,
        entity_ref_type=entity_ref_type,
        entity_ref_id=entity_ref_id,
        stage=stage,
        event_type=event_type,
        outcome=outcome,
        error_code=error_code,
        counters=counters if counters is not None else {},
        refs=refs if refs is not None else {},
    )
    validate_event(event)
    return event


def build_handler_started(
    *,
    module: str,
    work_item_id: str,
    entity_ref_type: str,
    entity_ref_id: str,
    stage: str,
    refs: dict[str, Any] | None = None,
) -> StructuredEventData:
    """Convenience builder for the mandatory handler_started event."""
    return build_event(
        module=module,
        work_item_id=work_item_id,
        entity_ref_type=entity_ref_type,
        entity_ref_id=entity_ref_id,
        stage=stage,
        event_type="handler_started",
        outcome="ok",
        refs=refs,
    )


def build_terminal_event(
    *,
    module: str,
    work_item_id: str,
    entity_ref_type: str,
    entity_ref_id: str,
    stage: str,
    event_type: str,
    outcome: str,
    error_code: str | None = None,
    counters: dict[str, int | float] | None = None,
    refs: dict[str, Any] | None = None,
) -> StructuredEventData:
    """
    Convenience builder for a terminal outcome event.

    event_type must be one of TERMINAL_EVENT_TYPES.
    """
    if event_type not in TERMINAL_EVENT_TYPES:
        raise ValueError(
            f"event_type {event_type!r} is not a terminal event type. "
            f"Must be one of: {sorted(TERMINAL_EVENT_TYPES)}"
        )
    return build_event(
        module=module,
        work_item_id=work_item_id,
        entity_ref_type=entity_ref_type,
        entity_ref_id=entity_ref_id,
        stage=stage,
        event_type=event_type,
        outcome=outcome,
        error_code=error_code,
        counters=counters,
        refs=refs,
    )


# ── DB emit (SQLAlchemy text — no aose_api import) ────────────────────────────


def emit(session: Any, event: StructuredEventData) -> None:
    """
    Validate and persist a StructuredEventData to the structured_events table.

    Uses a text() INSERT to avoid importing aose_api models into the worker.
    The session must be a SQLAlchemy Session or Connection backed by Postgres.

    Structured event writes must not be counted against the attempt budget
    (CONTRACT.yaml attempt_budget.decrement_rule.do_not_decrement_on).
    """
    import json  # noqa: PLC0415

    from sqlalchemy import text  # noqa: PLC0415

    validate_event(event)

    sql = text(
        """
        INSERT INTO structured_events (
            event_id, occurred_at, module, work_item_id,
            entity_ref_type, entity_ref_id, stage,
            event_type, outcome, error_code,
            counters, refs, v
        ) VALUES (
            :event_id, :occurred_at, :module, :work_item_id,
            :entity_ref_type, :entity_ref_id, :stage,
            :event_type, :outcome, :error_code,
            :counters, :refs, :v
        )
        """
    )
    session.execute(
        sql,
        {
            "event_id": event.event_id,
            "occurred_at": event.occurred_at,
            "module": event.module,
            "work_item_id": event.work_item_id,
            "entity_ref_type": event.entity_ref_type,
            "entity_ref_id": event.entity_ref_id,
            "stage": event.stage,
            "event_type": event.event_type,
            "outcome": event.outcome,
            "error_code": event.error_code,
            "counters": json.dumps(event.counters),
            "refs": json.dumps(event.refs),
            "v": event.v,
        },
    )
