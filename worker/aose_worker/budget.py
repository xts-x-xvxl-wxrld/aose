"""
Attempt budget policy for the AOSE worker pipeline.

Enforces CONTRACT.yaml attempt_budget rules:
  - decrement only on source_call and model_call
  - no decrement on validation, parsing, idempotency checks, DB reads,
    routing decisions, or structured event writes
  - budget exhaustion parks with parked:budget_exhausted, no retry
  - transient_error may retry only while budget remains
  - all other error codes must not retry

This module is the single source of truth for budget enforcement.
Handlers must not implement their own conflicting budget logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# ── Canonical attempt types ──────────────────────────────────────────────────
# Only these two types decrement the attempt budget (CONTRACT.yaml
# attempt_budget.decrement_rule.decrement_only_on).


class AttemptType(str, Enum):
    SOURCE_CALL = "source_call"
    MODEL_CALL = "model_call"


# ── Non-spending call types (budget must NOT decrement for these) ─────────────
# Enumerated for documentation and test verification only.
# Handlers that perform only these operations must not call spend_budget().

NON_SPENDING_OPERATIONS = frozenset(
    {
        "local_validation",
        "payload_parsing",
        "idempotency_existence_check",
        "db_read_only",
        "routing_decision",
        "structured_event_write",
    }
)


# ── Exhaustion outcome constants ─────────────────────────────────────────────
# CONTRACT.yaml attempt_budget.exhaustion_rule

BUDGET_EXHAUSTED_ERROR_CODE = "budget_exhausted"
BUDGET_EXHAUSTED_STAGE = "parked:budget_exhausted"
BUDGET_EXHAUSTED_TERMINAL_EVENT = "work_item_parked"


# ── Error codes that forbid retry ────────────────────────────────────────────
# CONTRACT.yaml attempt_budget.retry_rules — retry_allowed: false entries.
# transient_error is the only error code that may retry (while budget > 0).

NO_RETRY_ERROR_CODES = frozenset(
    {
        "contract_error",
        "budget_exhausted",
        "no_signal",
        "policy_blocked",
        "needs_human",
    }
)


# ── Core budget types ────────────────────────────────────────────────────────


class BudgetExhaustedError(Exception):
    """
    Raised when a handler attempts budget-spending work with remaining = 0.

    Callers must catch this and produce the canonical exhaustion outcome:
      error_code       = budget_exhausted
      stage_result     = parked:budget_exhausted
      terminal_event   = work_item_parked
      retry_allowed    = False
    """

    def __init__(self, remaining: int) -> None:
        super().__init__(
            f"Attempt budget exhausted (remaining={remaining}). "
            f"Park as {BUDGET_EXHAUSTED_STAGE!r}."
        )
        self.remaining = remaining


@dataclass(frozen=True)
class ExhaustionOutcome:
    """Terminal outcome produced when budget reaches zero."""

    error_code: str = BUDGET_EXHAUSTED_ERROR_CODE
    stage_result: str = BUDGET_EXHAUSTED_STAGE
    terminal_event_type: str = BUDGET_EXHAUSTED_TERMINAL_EVENT
    retry_allowed: bool = False


@dataclass(frozen=True)
class SpendResult:
    """Result of a successful budget decrement."""

    remaining_after: int
    attempt_type: AttemptType


# ── Public API ───────────────────────────────────────────────────────────────


def check_budget(remaining: int) -> None:
    """
    Assert the budget has capacity before performing budget-spending work.

    Raises BudgetExhaustedError if remaining == 0.
    Must be called before every source_call or model_call attempt.
    Must NOT be called for non-spending operations (validation, reads, routing).
    """
    if remaining <= 0:
        raise BudgetExhaustedError(remaining)


def spend_budget(remaining: int, attempt_type: AttemptType) -> SpendResult:
    """
    Decrement the attempt budget by one for a budget-spending operation.

    Args:
        remaining:    current attempt_budget_remaining from the WorkItem.
        attempt_type: must be AttemptType.SOURCE_CALL or AttemptType.MODEL_CALL.

    Returns:
        SpendResult with the new remaining value.

    Raises:
        BudgetExhaustedError if remaining is already 0.
        TypeError if attempt_type is not an AttemptType member.
    """
    if not isinstance(attempt_type, AttemptType):
        raise TypeError(
            f"attempt_type must be an AttemptType member, got {attempt_type!r}. "
            "Only source_call and model_call may decrement the budget."
        )
    check_budget(remaining)
    return SpendResult(remaining_after=remaining - 1, attempt_type=attempt_type)


def exhaustion_outcome() -> ExhaustionOutcome:
    """
    Return the canonical terminal outcome for budget exhaustion.

    Handlers must use this rather than constructing their own outcome,
    to ensure the stage_result, error_code, and event type are canonical.
    """
    return ExhaustionOutcome()


def is_retry_allowed(error_code: str, remaining: int) -> bool:
    """
    Determine whether a failed work item may be re-enqueued for retry.

    Rules (CONTRACT.yaml attempt_budget.retry_rules):
      - transient_error → retry only while remaining > 0
      - all other error codes → no retry regardless of remaining

    Args:
        error_code: the canonical error code from the handler outcome.
        remaining:  current attempt_budget_remaining.

    Returns:
        True only if retry is allowed by both error code and budget rules.
    """
    if error_code in NO_RETRY_ERROR_CODES:
        return False
    if error_code == "transient_error":
        return remaining > 0
    # Unknown error codes are conservatively treated as no-retry.
    return False


def should_decrement_budget(
    operation: str, *, is_idempotent_noop: bool = False
) -> bool:
    """
    Return whether a handler operation should decrement attempt budget.

    Budget is spent only on source/model calls and never on idempotent no-op replays.
    """
    if is_idempotent_noop:
        return False
    return operation in {AttemptType.SOURCE_CALL.value, AttemptType.MODEL_CALL.value}
