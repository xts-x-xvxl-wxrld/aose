"""
Stage router for the AOSE worker pipeline.

Implements table-driven explicit routing per CONTRACT.yaml:
  - routing.router_model = table_driven_explicit_registry
  - routing.exact_match_rule (no fuzzy, no alias, no reflection)
  - routing.parked_stage_rule
  - routing.unknown_stage_rule

Router may return only one of:
  - handler_dispatch
  - parked_terminal
  - contract_failure
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from aose_worker.registry import HANDLER_REGISTRY, HandlerFn

PARKED_PREFIX = "parked:"


class RouteResultType(str, Enum):
    HANDLER_DISPATCH = "handler_dispatch"
    PARKED_TERMINAL = "parked_terminal"
    CONTRACT_FAILURE = "contract_failure"


@dataclass(frozen=True)
class RouteResult:
    result_type: RouteResultType
    stage: str
    handler: HandlerFn | None = field(default=None, compare=False)
    error_code: str | None = None
    terminal_event_type: str | None = None


def route(stage: str) -> RouteResult:
    """
    Resolve routing for a given WorkItem.stage.

    Resolution order (CONTRACT.yaml routing section):

    1. stage starts with "parked:" → parked_terminal
       - do not dispatch to any normal handler
       - treat as terminal route
       - preserve parked reason suffix exactly

    2. stage is an exact key in HANDLER_REGISTRY → handler_dispatch
       - no normalization, no alias lookup, no fuzzy matching

    3. anything else → contract_failure
       - error_code = contract_error
       - terminal_event_type = work_item_failed_contract
       - retry_allowed = false (caller must not re-enqueue)
    """
    # Rule 1: parked stage — terminal, ack cleanly, no handler dispatch
    if stage.startswith(PARKED_PREFIX):
        return RouteResult(
            result_type=RouteResultType.PARKED_TERMINAL,
            stage=stage,
            terminal_event_type="work_item_parked",
        )

    # Rule 2: exact canonical match only
    handler: HandlerFn | None = HANDLER_REGISTRY.get(stage)
    if handler is not None:
        return RouteResult(
            result_type=RouteResultType.HANDLER_DISPATCH,
            stage=stage,
            handler=handler,
        )

    # Rule 3: unknown stage — contract failure, no retry
    return RouteResult(
        result_type=RouteResultType.CONTRACT_FAILURE,
        stage=stage,
        error_code="contract_error",
        terminal_event_type="work_item_failed_contract",
    )
