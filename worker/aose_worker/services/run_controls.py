"""
Run controls for Epic E account discovery (SPEC-E4).

Centralizes deterministic cap resolution and stop-rule evaluation so the
handler/service can enforce one canonical policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PH_EPIC_E_002_DEFAULT_MAX_ACCOUNTS_PER_QUERY_OBJECT = 10

LOCKED_MAX_ACCOUNTS_PER_RUN = 30
LOCKED_MAX_EXTERNAL_CALLS_PER_RUN = 250
LOCKED_MAX_RUNTIME_SECONDS_PER_RUN = 900
LOCKED_MAX_QUERIES_PER_RUN_DEFAULT = 10
LOCKED_TIMEOUT_SECONDS = 20
LOCKED_RETRY_COUNT_TRANSIENT = 2
LOCKED_BACKOFF_SECONDS = (2, 8)


@dataclass(frozen=True)
class RunLimits:
    max_accounts_per_run: int = LOCKED_MAX_ACCOUNTS_PER_RUN
    max_external_calls_per_run: int = LOCKED_MAX_EXTERNAL_CALLS_PER_RUN
    max_runtime_seconds_per_run: int = LOCKED_MAX_RUNTIME_SECONDS_PER_RUN
    max_queries_per_run: int = LOCKED_MAX_QUERIES_PER_RUN_DEFAULT
    max_accounts_per_query_object: int = (
        PH_EPIC_E_002_DEFAULT_MAX_ACCOUNTS_PER_QUERY_OBJECT
    )
    timeout_seconds: int = LOCKED_TIMEOUT_SECONDS


@dataclass(frozen=True)
class RetryPolicy:
    retry_count_transient: int = LOCKED_RETRY_COUNT_TRANSIENT
    backoff_seconds: tuple[int, int] = LOCKED_BACKOFF_SECONDS


def _coerce_positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def resolve_run_limits(run_limits_override: dict[str, Any] | None = None) -> RunLimits:
    """
    Resolve run caps using locked defaults plus optional overrides.

    Overrides are best-effort and only applied for known fields when positive ints.
    """
    override = run_limits_override or {}
    return RunLimits(
        max_accounts_per_run=_coerce_positive_int(
            override.get("max_accounts_per_run"), LOCKED_MAX_ACCOUNTS_PER_RUN
        ),
        max_external_calls_per_run=_coerce_positive_int(
            override.get("max_external_calls_per_run"),
            LOCKED_MAX_EXTERNAL_CALLS_PER_RUN,
        ),
        max_runtime_seconds_per_run=_coerce_positive_int(
            override.get("max_runtime_seconds_per_run"),
            LOCKED_MAX_RUNTIME_SECONDS_PER_RUN,
        ),
        max_queries_per_run=_coerce_positive_int(
            override.get("max_queries_per_run"), LOCKED_MAX_QUERIES_PER_RUN_DEFAULT
        ),
        max_accounts_per_query_object=_coerce_positive_int(
            override.get("max_accounts_per_query_object"),
            PH_EPIC_E_002_DEFAULT_MAX_ACCOUNTS_PER_QUERY_OBJECT,
        ),
        timeout_seconds=_coerce_positive_int(
            override.get("timeout_seconds"), LOCKED_TIMEOUT_SECONDS
        ),
    )


def resolve_retry_policy() -> RetryPolicy:
    """Return the locked transient retry policy."""
    return RetryPolicy()


def transient_backoff_for_attempt(attempt_number: int) -> int | None:
    """
    Return deterministic backoff seconds for transient retries.

    attempt_number is 1-based retry attempt index.
    Returns None when no further retry is allowed.
    """
    policy = resolve_retry_policy()
    if attempt_number < 1 or attempt_number > policy.retry_count_transient:
        return None
    return policy.backoff_seconds[attempt_number - 1]


def evaluate_stop_rule(
    *,
    limits: RunLimits,
    elapsed_seconds: float,
    external_calls_used: int,
    queries_used: int,
    accounts_created_this_query: int,
) -> str | None:
    """
    Evaluate deterministic E4 stop rules for a single-query work item.

    Returns one of:
      - budget_exhausted
      - max_accounts_reached
      - no_signal
      - None
    """
    if elapsed_seconds >= limits.max_runtime_seconds_per_run:
        return "budget_exhausted"
    if external_calls_used >= limits.max_external_calls_per_run:
        return "budget_exhausted"
    if queries_used >= limits.max_queries_per_run:
        return "budget_exhausted"
    if (
        accounts_created_this_query >= limits.max_accounts_per_query_object
        or accounts_created_this_query >= limits.max_accounts_per_run
    ):
        return "max_accounts_reached"
    if accounts_created_this_query == 0:
        return "no_signal"
    return None
