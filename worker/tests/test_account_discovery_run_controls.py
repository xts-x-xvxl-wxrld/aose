"""Unit tests for SPEC-E4 run controls."""

from __future__ import annotations

from aose_worker.budget import should_decrement_budget
from aose_worker.services.run_controls import (
    LOCKED_BACKOFF_SECONDS,
    LOCKED_RETRY_COUNT_TRANSIENT,
    PH_EPIC_E_002_DEFAULT_MAX_ACCOUNTS_PER_QUERY_OBJECT,
    evaluate_stop_rule,
    resolve_retry_policy,
    resolve_run_limits,
    transient_backoff_for_attempt,
)


def test_per_query_object_cap_defaults_to_placeholder_value_10():
    limits = resolve_run_limits()
    assert (
        limits.max_accounts_per_query_object
        == PH_EPIC_E_002_DEFAULT_MAX_ACCOUNTS_PER_QUERY_OBJECT
        == 10
    )


def test_run_limits_override_applies_positive_values_only():
    limits = resolve_run_limits(
        {
            "max_accounts_per_query_object": 7,
            "max_runtime_seconds_per_run": -1,
            "max_external_calls_per_run": "12",
        }
    )
    assert limits.max_accounts_per_query_object == 7
    assert limits.max_external_calls_per_run == 12
    # negative override should be ignored -> locked default
    assert limits.max_runtime_seconds_per_run == 900


def test_retry_policy_locked_values():
    policy = resolve_retry_policy()
    assert policy.retry_count_transient == LOCKED_RETRY_COUNT_TRANSIENT == 2
    assert policy.backoff_seconds == LOCKED_BACKOFF_SECONDS == (2, 8)


def test_transient_backoff_respects_two_retries():
    assert transient_backoff_for_attempt(1) == 2
    assert transient_backoff_for_attempt(2) == 8
    assert transient_backoff_for_attempt(3) is None


def test_external_call_accounting_decrements_only_meaningful_attempts():
    assert should_decrement_budget("source_call") is True
    assert should_decrement_budget("model_call") is True
    assert should_decrement_budget("db_read_only") is False
    assert should_decrement_budget("source_call", is_idempotent_noop=True) is False


def test_stop_rule_budget_exhausted_on_runtime_cap():
    limits = resolve_run_limits({"max_runtime_seconds_per_run": 1})
    stop = evaluate_stop_rule(
        limits=limits,
        elapsed_seconds=1.0,
        external_calls_used=0,
        queries_used=1,
        accounts_created_this_query=0,
    )
    assert stop == "budget_exhausted"


def test_stop_rule_no_signal_when_zero_new_unique_accounts():
    limits = resolve_run_limits()
    stop = evaluate_stop_rule(
        limits=limits,
        elapsed_seconds=0.1,
        external_calls_used=1,
        queries_used=1,
        accounts_created_this_query=0,
    )
    assert stop == "no_signal"
