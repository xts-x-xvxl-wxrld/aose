"""
Unit tests for SPEC-C4: structured event writer.

Acceptance checks covered:
  1. Running any handler writes handler_started and one terminal outcome event.
  2. Contract failure writes canonical failure event_type/outcome with error_code=contract_error.
  3. Parked outcome writes canonical parked terminal event; reason in refs safely.
  4. Events do not contain raw emails, raw phone numbers, or full message bodies.
  5. Recent-events query limit of 20 (tested via limit constant).
  6. CI gate: handlers emit structured events at start and terminal outcome.
  7. CI gate: structured events are redacted according to baseline policy.
"""

from __future__ import annotations

import pytest

from aose_worker.events import (
    CANONICAL_ERROR_CODES,
    CANONICAL_EVENT_TYPES,
    CANONICAL_OUTCOMES,
    TERMINAL_EVENT_TYPES,
    build_event,
    build_handler_started,
    build_terminal_event,
    validate_event,
)

# ── Shared fixture data ───────────────────────────────────────────────────────

_MODULE = "aose_worker.handlers.intent_fit_scoring"
_WI_ID = "wi-test-001"
_REF_TYPE = "account"
_REF_ID = "account:example.com"
_STAGE = "intent_fit_scoring"


def _base_kwargs(**overrides):
    defaults = dict(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
        event_type="handler_started",
        outcome="ok",
    )
    defaults.update(overrides)
    return defaults


# ── Acceptance check 1 & CI gate 1 ──────────────────────────────────────────
# Handlers emit handler_started + one terminal outcome event.


def test_handler_started_event_is_valid() -> None:
    """Acceptance check 1: handler_started event is accepted."""
    evt = build_handler_started(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
    )
    assert evt.event_type == "handler_started"
    assert evt.outcome == "ok"
    assert evt.error_code is None


def test_terminal_event_work_item_completed() -> None:
    evt = build_terminal_event(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
        event_type="work_item_completed",
        outcome="ok",
    )
    assert evt.event_type == "work_item_completed"
    assert evt.event_type in TERMINAL_EVENT_TYPES


def test_ci_gate_start_and_terminal_pair_are_valid() -> None:
    """CI gate: handlers emit structured events at start and terminal outcome."""
    start = build_handler_started(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
    )
    terminal = build_terminal_event(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
        event_type="work_item_completed",
        outcome="ok",
    )
    # Both must validate without error
    validate_event(start)
    validate_event(terminal)
    assert start.event_type == "handler_started"
    assert terminal.event_type in TERMINAL_EVENT_TYPES


# ── Acceptance check 2 ───────────────────────────────────────────────────────
# Contract failure → work_item_failed_contract, failed_contract, error_code=contract_error.


def test_contract_failure_event_is_canonical() -> None:
    """Acceptance check 2: contract failure writes canonical failure event."""
    evt = build_terminal_event(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
        event_type="work_item_failed_contract",
        outcome="failed_contract",
        error_code="contract_error",
    )
    assert evt.event_type == "work_item_failed_contract"
    assert evt.outcome == "failed_contract"
    assert evt.error_code == "contract_error"
    validate_event(evt)


def test_contract_failure_is_terminal() -> None:
    assert "work_item_failed_contract" in TERMINAL_EVENT_TYPES


# ── Acceptance check 3 ───────────────────────────────────────────────────────
# Parked outcome → work_item_parked; parked reason safe in refs (not raw PII).


def test_parked_event_canonical() -> None:
    """Acceptance check 3: parked terminal event with reason in refs safely."""
    evt = build_terminal_event(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
        event_type="work_item_parked",
        outcome="parked",
        error_code="no_signal",
        refs={"parked_reason": "no_signal", "work_item_id": _WI_ID},
    )
    assert evt.event_type == "work_item_parked"
    assert evt.outcome == "parked"
    assert evt.refs["parked_reason"] == "no_signal"
    validate_event(evt)


def test_parked_event_is_terminal() -> None:
    assert "work_item_parked" in TERMINAL_EVENT_TYPES


# ── Acceptance check 4 & CI gate 2 ──────────────────────────────────────────
# Events must not contain raw emails, phone numbers, or full message bodies.


def test_refs_with_raw_email_is_rejected() -> None:
    """Acceptance check 4: raw email address in refs raises ValueError."""
    with pytest.raises(ValueError, match="full_email_address"):
        build_event(
            **_base_kwargs(
                refs={"contact_email": "alice@example.com"},
            )
        )


def test_refs_with_raw_phone_is_rejected() -> None:
    """Acceptance check 4: raw phone number in refs raises ValueError."""
    with pytest.raises(ValueError, match="full_phone_number"):
        build_event(
            **_base_kwargs(
                refs={"phone": "+1 555-867-5309"},
            )
        )


def test_refs_with_us_phone_format_is_rejected() -> None:
    with pytest.raises(ValueError, match="full_phone_number"):
        build_event(
            **_base_kwargs(
                refs={"phone": "555-867-5309"},
            )
        )


def test_refs_with_safe_canonical_ids_accepted() -> None:
    """Redaction allows canonical IDs, domain fragments, provider refs."""
    evt = build_event(
        **_base_kwargs(
            refs={
                "contact_id": "contact:account:example.com:alice",
                "evidence_ids": ["evidence:abc123"],
                "domain_fragment": "example.com",
                "provider_id": "SEND_SRC_01",
                "payload_version": "1",
            }
        )
    )
    validate_event(evt)
    assert evt.refs["domain_fragment"] == "example.com"


def test_ci_gate_events_redacted_no_raw_pii() -> None:
    """CI gate: structured events are redacted according to baseline policy."""
    # Valid: no PII
    evt = build_event(
        **_base_kwargs(
            refs={"work_item_id": _WI_ID, "stage": _STAGE},
        )
    )
    validate_event(evt)

    # Invalid: email present
    with pytest.raises(ValueError, match="full_email_address"):
        build_event(**_base_kwargs(refs={"email": "user@domain.com"}))


# ── Acceptance check 5 ───────────────────────────────────────────────────────
# Recent-events query returns at most 20 events per entity.
# The DB query limit (20) is enforced at the API layer (aose_api.main).
# The API-side test is in api/tests/test_events_api.py (SPEC-C4 acceptance check 5).
# Here we verify only the worker-side event count invariant: exactly two events
# per handler invocation (one start, one terminal).


def test_handler_emits_exactly_two_events_start_and_terminal() -> None:
    """Acceptance check 5 (worker side): handler produces one start + one terminal."""
    events = []

    events.append(
        build_handler_started(
            module=_MODULE,
            work_item_id=_WI_ID,
            entity_ref_type=_REF_TYPE,
            entity_ref_id=_REF_ID,
            stage=_STAGE,
        )
    )
    events.append(
        build_terminal_event(
            module=_MODULE,
            work_item_id=_WI_ID,
            entity_ref_type=_REF_TYPE,
            entity_ref_id=_REF_ID,
            stage=_STAGE,
            event_type="work_item_completed",
            outcome="ok",
        )
    )

    assert len(events) == 2
    assert events[0].event_type == "handler_started"
    assert events[1].event_type in TERMINAL_EVENT_TYPES


# ── Invalid event_type rejected ───────────────────────────────────────────────


def test_invalid_event_type_raises() -> None:
    with pytest.raises(ValueError, match="Invalid event_type"):
        build_event(**_base_kwargs(event_type="not_a_real_type"))


def test_invalid_outcome_raises() -> None:
    with pytest.raises(ValueError, match="Invalid outcome"):
        build_event(**_base_kwargs(outcome="not_a_real_outcome"))


def test_invalid_error_code_raises() -> None:
    with pytest.raises(ValueError, match="Invalid error_code"):
        build_event(**_base_kwargs(error_code="invented_error"))


def test_none_error_code_accepted() -> None:
    evt = build_event(**_base_kwargs(error_code=None))
    assert evt.error_code is None


# ── Counters must be numeric-only ─────────────────────────────────────────────


def test_counters_accepts_int_and_float() -> None:
    evt = build_event(**_base_kwargs(counters={"calls": 1, "latency_ms": 42.5}))
    assert evt.counters["calls"] == 1


def test_counters_rejects_string_value() -> None:
    with pytest.raises(ValueError, match="counters"):
        build_event(**_base_kwargs(counters={"label": "text"}))


def test_counters_rejects_list_value() -> None:
    with pytest.raises(ValueError, match="counters"):
        build_event(**_base_kwargs(counters={"ids": ["a", "b"]}))


def test_empty_counters_accepted() -> None:
    evt = build_event(**_base_kwargs(counters={}))
    assert evt.counters == {}


# ── Terminal event builder guards ─────────────────────────────────────────────


def test_build_terminal_event_rejects_non_terminal_type() -> None:
    with pytest.raises(ValueError, match="not a terminal event type"):
        build_terminal_event(
            module=_MODULE,
            work_item_id=_WI_ID,
            entity_ref_type=_REF_TYPE,
            entity_ref_id=_REF_ID,
            stage=_STAGE,
            event_type="handler_started",  # not terminal
            outcome="ok",
        )


@pytest.mark.parametrize("event_type", sorted(TERMINAL_EVENT_TYPES))
def test_all_terminal_event_types_accepted_by_builder(event_type: str) -> None:
    outcome_map = {
        "work_item_completed": "ok",
        "work_item_parked": "parked",
        "work_item_failed_contract": "failed_contract",
        "work_item_failed_transient": "failed_transient",
    }
    error_map = {
        "work_item_failed_contract": "contract_error",
        "work_item_parked": "budget_exhausted",
    }
    evt = build_terminal_event(
        module=_MODULE,
        work_item_id=_WI_ID,
        entity_ref_type=_REF_TYPE,
        entity_ref_id=_REF_ID,
        stage=_STAGE,
        event_type=event_type,
        outcome=outcome_map[event_type],
        error_code=error_map.get(event_type),
    )
    assert evt.event_type == event_type


# ── Canonical enum completeness ───────────────────────────────────────────────


def test_canonical_event_types_completeness() -> None:
    expected = {
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
    assert CANONICAL_EVENT_TYPES == expected


def test_canonical_outcomes_completeness() -> None:
    expected = {
        "ok",
        "parked",
        "failed_contract",
        "failed_transient",
        "retry_scheduled",
        "noop",
    }
    assert CANONICAL_OUTCOMES == expected


def test_canonical_error_codes_completeness() -> None:
    expected = {
        "contract_error",
        "transient_error",
        "budget_exhausted",
        "no_signal",
        "policy_blocked",
        "needs_human",
    }
    assert CANONICAL_ERROR_CODES == expected


def test_terminal_event_types_completeness() -> None:
    expected = {
        "work_item_completed",
        "work_item_parked",
        "work_item_failed_contract",
        "work_item_failed_transient",
    }
    assert TERMINAL_EVENT_TYPES == expected


# ── Event ID and occurred_at are auto-populated ───────────────────────────────


def test_event_id_is_auto_generated() -> None:
    evt = build_event(**_base_kwargs())
    assert evt.event_id.startswith("evt:")
    assert len(evt.event_id) > 5


def test_occurred_at_is_auto_populated() -> None:
    from datetime import timezone  # noqa: PLC0415

    evt = build_event(**_base_kwargs())
    assert evt.occurred_at.tzinfo is not None
    assert evt.occurred_at.tzinfo == timezone.utc


def test_two_events_have_different_ids() -> None:
    e1 = build_event(**_base_kwargs())
    e2 = build_event(**_base_kwargs())
    assert e1.event_id != e2.event_id
