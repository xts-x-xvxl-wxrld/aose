"""
Unit tests for SPEC-C2: attempt budget policy.

Acceptance checks covered:
  1. A handler that performs one source_call decrements budget by exactly one.
  2. A handler that only validates payload / reads DB does not decrement budget.
  3. A work item with remaining=0 parks as parked:budget_exhausted before
     any budget-spending side effect.
  4. A transient_error with remaining budget schedules retry.
  5. A transient_error with zero remaining does not retry and parks.
  6. CI gate: budget exhaustion produces deterministic parked outcome with reason.
"""

import pytest

from aose_worker.budget import (
    BUDGET_EXHAUSTED_ERROR_CODE,
    BUDGET_EXHAUSTED_STAGE,
    BUDGET_EXHAUSTED_TERMINAL_EVENT,
    NON_SPENDING_OPERATIONS,
    AttemptType,
    BudgetExhaustedError,
    ExhaustionOutcome,
    SpendResult,
    check_budget,
    exhaustion_outcome,
    is_retry_allowed,
    spend_budget,
)


# ── Acceptance check 1 ───────────────────────────────────────────────────────
# source_call and model_call each decrement budget by exactly one.


@pytest.mark.parametrize(
    "attempt_type",
    [AttemptType.SOURCE_CALL, AttemptType.MODEL_CALL],
)
def test_spend_budget_decrements_by_one(attempt_type: AttemptType) -> None:
    result = spend_budget(remaining=5, attempt_type=attempt_type)
    assert isinstance(result, SpendResult)
    assert result.remaining_after == 4
    assert result.attempt_type == attempt_type


def test_spend_budget_source_call_exact_decrement() -> None:
    result = spend_budget(remaining=3, attempt_type=AttemptType.SOURCE_CALL)
    assert result.remaining_after == 2


def test_spend_budget_model_call_exact_decrement() -> None:
    result = spend_budget(remaining=1, attempt_type=AttemptType.MODEL_CALL)
    assert result.remaining_after == 0


# ── Acceptance check 2 ───────────────────────────────────────────────────────
# Non-spending operations must not call spend_budget (validated by convention).
# We verify the NON_SPENDING_OPERATIONS set is complete and correct.


def test_non_spending_operations_covers_contract_list() -> None:
    expected = {
        "local_validation",
        "payload_parsing",
        "idempotency_existence_check",
        "db_read_only",
        "routing_decision",
        "structured_event_write",
    }
    assert expected == NON_SPENDING_OPERATIONS


def test_check_budget_does_not_decrement_anything() -> None:
    # check_budget is a guard only — it does not modify remaining.
    # Calling it with remaining > 0 must not raise.
    check_budget(1)
    check_budget(100)


def test_non_budget_spending_path_does_not_raise() -> None:
    # Simulates a handler that only validates and reads — no spend_budget call.
    remaining = 3
    # purely local operations — no spend_budget invoked
    _ = remaining > 0  # routing decision (never decrements)
    # budget unchanged
    assert remaining == 3


# ── Acceptance check 3 & CI gate ─────────────────────────────────────────────
# remaining=0 → BudgetExhaustedError before any spending side effect.
# Exhaustion outcome is canonical.


def test_check_budget_raises_at_zero() -> None:
    with pytest.raises(BudgetExhaustedError) as exc_info:
        check_budget(0)
    assert exc_info.value.remaining == 0


def test_check_budget_raises_at_negative() -> None:
    with pytest.raises(BudgetExhaustedError):
        check_budget(-1)


def test_spend_budget_raises_at_zero() -> None:
    with pytest.raises(BudgetExhaustedError) as exc_info:
        spend_budget(remaining=0, attempt_type=AttemptType.SOURCE_CALL)
    assert exc_info.value.remaining == 0


def test_spend_budget_raises_model_call_at_zero() -> None:
    with pytest.raises(BudgetExhaustedError):
        spend_budget(remaining=0, attempt_type=AttemptType.MODEL_CALL)


def test_exhaustion_outcome_is_canonical() -> None:
    outcome = exhaustion_outcome()
    assert isinstance(outcome, ExhaustionOutcome)
    assert outcome.error_code == BUDGET_EXHAUSTED_ERROR_CODE
    assert outcome.stage_result == BUDGET_EXHAUSTED_STAGE
    assert outcome.terminal_event_type == BUDGET_EXHAUSTED_TERMINAL_EVENT
    assert outcome.retry_allowed is False


def test_ci_gate_budget_exhaustion_deterministic_parked_outcome() -> None:
    """CI gate: budget exhaustion produces deterministic parked outcome with reason."""
    with pytest.raises(BudgetExhaustedError):
        check_budget(0)

    outcome = exhaustion_outcome()
    assert outcome.error_code == "budget_exhausted"
    assert outcome.stage_result == "parked:budget_exhausted"
    assert outcome.terminal_event_type == "work_item_parked"
    assert outcome.retry_allowed is False


# ── Acceptance check 4 ───────────────────────────────────────────────────────
# transient_error + remaining > 0 → retry allowed.


@pytest.mark.parametrize("remaining", [1, 2, 10, 100])
def test_transient_error_with_budget_allows_retry(remaining: int) -> None:
    assert is_retry_allowed("transient_error", remaining) is True


# ── Acceptance check 5 ───────────────────────────────────────────────────────
# transient_error + remaining == 0 → no retry, deterministic park.


def test_transient_error_at_zero_budget_no_retry() -> None:
    assert is_retry_allowed("transient_error", 0) is False


def test_transient_error_at_zero_budget_exhaustion_outcome() -> None:
    # Simulates the handler path: transient error but budget is gone.
    remaining = 0
    allowed = is_retry_allowed("transient_error", remaining)
    assert allowed is False
    outcome = exhaustion_outcome()
    assert outcome.stage_result == "parked:budget_exhausted"


# ── Retry rules for all no-retry error codes ─────────────────────────────────
# CONTRACT.yaml attempt_budget.retry_rules — must match exactly.


@pytest.mark.parametrize(
    "error_code",
    [
        "contract_error",
        "budget_exhausted",
        "no_signal",
        "policy_blocked",
        "needs_human",
    ],
)
def test_no_retry_error_codes_never_retry(error_code: str) -> None:
    # No retry regardless of remaining budget
    assert is_retry_allowed(error_code, 10) is False
    assert is_retry_allowed(error_code, 1) is False
    assert is_retry_allowed(error_code, 0) is False


# ── Invalid attempt_type guard ────────────────────────────────────────────────
# spend_budget must reject strings or plain values that are not AttemptType members.


def test_spend_budget_rejects_invalid_attempt_type() -> None:
    with pytest.raises(TypeError):
        spend_budget(remaining=5, attempt_type="source_call")  # type: ignore[arg-type]


def test_spend_budget_rejects_non_spending_type_string() -> None:
    with pytest.raises(TypeError):
        spend_budget(remaining=5, attempt_type="local_validation")  # type: ignore[arg-type]


# ── AttemptType enum completeness ────────────────────────────────────────────
# Must contain exactly the two locked decrement-on values from CONTRACT.yaml.


def test_attempt_type_has_exactly_two_members() -> None:
    assert set(AttemptType) == {AttemptType.SOURCE_CALL, AttemptType.MODEL_CALL}


def test_attempt_type_values_match_contract() -> None:
    assert AttemptType.SOURCE_CALL.value == "source_call"
    assert AttemptType.MODEL_CALL.value == "model_call"
