"""
Unit tests for SPEC-C1: deterministic stage router.

Acceptance checks covered:
  1. Known canonical stage dispatches to registered handler (handler_dispatch).
  2. Parked stage (parked:no_signal) returns parked_terminal; no normal handler.
  3. Hyphenated alias (intent-fit-scoring) fails as contract_failure (no fuzzy).
  4. Unknown stages produce contract_failure with error_code=contract_error.
  5. CI gate: unknown stage → contract_error + work_item_failed_contract event type.
  6. CI gate: parked stage never dispatches to a normal handler.
"""

import pytest

from aose_worker.registry import HANDLER_REGISTRY
from aose_worker.router import PARKED_PREFIX, RouteResultType, route


# ── Acceptance check 1 ──────────────────────────────────────────────────────
# Known canonical stage → handler_dispatch to registered handler.


@pytest.mark.parametrize("stage", list(HANDLER_REGISTRY.keys()))
def test_known_stage_dispatches(stage: str) -> None:
    result = route(stage)
    assert result.result_type == RouteResultType.HANDLER_DISPATCH
    assert result.handler is not None
    assert result.stage == stage
    assert result.error_code is None
    assert result.terminal_event_type is None


# ── Acceptance check 2 & CI gate 2 ──────────────────────────────────────────
# Parked stage → parked_terminal; no normal handler dispatched.


@pytest.mark.parametrize(
    "stage",
    [
        "parked:no_signal",
        "parked:budget_exhausted",
        "parked:policy_blocked",
        "parked:needs_human",
        "parked:contract_error",
        "parked:unknown_future_reason",
    ],
)
def test_parked_stage_is_terminal_no_handler(stage: str) -> None:
    assert stage.startswith(PARKED_PREFIX)
    result = route(stage)
    assert result.result_type == RouteResultType.PARKED_TERMINAL
    assert result.result_type != RouteResultType.HANDLER_DISPATCH
    assert result.handler is None
    assert result.stage == stage
    assert result.terminal_event_type == "work_item_parked"


# ── Acceptance check 3 ──────────────────────────────────────────────────────
# Hyphenated alias is not normalized — must fail as contract_failure.


def test_hyphenated_alias_rejected() -> None:
    result = route("intent-fit-scoring")
    assert result.result_type == RouteResultType.CONTRACT_FAILURE
    assert result.error_code == "contract_error"


# ── Acceptance check 4 & 5 & CI gate 1 ─────────────────────────────────────
# Unknown stages → contract_failure with correct error_code and terminal event.


@pytest.mark.parametrize(
    "stage",
    [
        "unknown_stage",
        "SELLER_PROFILE_BUILD",  # wrong case — no alias guessing
        "seller-profile-build",  # hyphenated — no normalization
        "",  # empty string
        "intent_fit_SCORING",  # mixed case
        " intent_fit_scoring",  # leading space
        "intent_fit_scoring ",  # trailing space
    ],
)
def test_unknown_stage_contract_failure(stage: str) -> None:
    result = route(stage)
    assert result.result_type == RouteResultType.CONTRACT_FAILURE
    assert result.error_code == "contract_error"
    assert result.terminal_event_type == "work_item_failed_contract"
    assert result.handler is None


def test_ci_gate_unknown_stage_emits_contract_error_and_failed_event() -> None:
    """CI gate: unknown stage becomes contract_error and emits structured failure event."""
    result = route("not_a_real_stage")
    assert result.result_type == RouteResultType.CONTRACT_FAILURE
    assert result.error_code == "contract_error"
    assert result.terminal_event_type == "work_item_failed_contract"


def test_ci_gate_parked_stage_no_normal_handler_dispatch() -> None:
    """CI gate: parked stage does not dispatch to a normal handler."""
    result = route("parked:no_signal")
    assert result.result_type != RouteResultType.HANDLER_DISPATCH
    assert result.handler is None


# ── Registry integrity ───────────────────────────────────────────────────────
# Confirm that the registry contains only canonical stage strings and no extras.


CANONICAL_STAGES = {
    "seller_profile_build",
    "query_objects_generate",
    "account_discovery",
    "intent_fit_scoring",
    "people_search",
    "contact_enrichment",
    "copy_generate",
    "approval_request",
    "sending_dispatch",
}


def test_registry_keys_are_exactly_canonical_stages() -> None:
    assert set(HANDLER_REGISTRY.keys()) == CANONICAL_STAGES


def test_no_parked_prefix_in_registry() -> None:
    for key in HANDLER_REGISTRY:
        assert not key.startswith(
            PARKED_PREFIX
        ), f"Registry must not contain parked-prefixed key: {key!r}"
