"""
Account discovery handler for the AOSE worker pipeline.

Registered in HANDLER_REGISTRY for stage 'account_discovery'.

Orchestration sequence:
  1. Load WorkItem from DB.
  2. Emit handler_started structured event.
  3. Validate payload preconditions (contract error → park immediately).
  4. Select adapter via registry (PH-EPIC-E-001 default: dummy_predictable).
  5. Enforce attempt budget before source call.
  6. Spend budget and persist updated remaining to DB.
  7. Call account discovery service.
  8. Commit canonical writes.
  9. Emit terminal structured event (completed / parked:no_signal).

Error routing (CONTRACT.yaml errors_and_routing):
  - missing QueryObject / SellerProfile     → parked:contract_error (no retry)
  - invalid adapter result                  → parked:contract_error (no retry)
  - budget_exhausted                        → parked:budget_exhausted (no retry)
  - transient failures                      → caller (RQ) retries while budget > 0
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.adapters.account_discovery.registry import get_adapter
from aose_worker.budget import (
    AttemptType,
    BudgetExhaustedError,
    check_budget,
    should_decrement_budget,
    spend_budget,
)
from aose_worker.events import (
    build_event,
    build_handler_started,
    build_terminal_event,
    emit,
)
from aose_worker.services.account_discovery_service import run_account_discovery
from aose_worker.services.run_controls import (
    evaluate_stop_rule,
    resolve_retry_policy,
    resolve_run_limits,
)

MODULE = "aose_worker.handlers.account_discovery"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


def _load_work_item(session: Any, work_item_id: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT work_item_id, stage, payload_json, payload_version,
               attempt_budget_remaining, attempt_budget_policy,
               entity_ref_type, entity_ref_id,
               trace_run_id, trace_parent_work_item_id,
               trace_correlation_id, trace_policy_pack_id
        FROM work_items
        WHERE work_item_id = :id
        """
    )
    row = session.execute(sql, {"id": work_item_id}).mappings().first()
    if row is None:
        raise ValueError(f"WorkItem not found: {work_item_id!r}")
    return dict(row)


def _set_work_item_stage(session: Any, work_item_id: str, stage: str) -> None:
    """Update a WorkItem stage deterministically."""
    session.execute(
        text("UPDATE work_items SET stage = :stage WHERE work_item_id = :id"),
        {"stage": stage, "id": work_item_id},
    )


def _has_terminal_event(session: Any, work_item_id: str) -> bool:
    """Return True if this WorkItem already has any terminal structured event."""
    sql = text(
        """
        SELECT 1
        FROM structured_events
        WHERE work_item_id = :id
          AND event_type IN (
            'work_item_completed',
            'work_item_parked',
            'work_item_failed_contract',
            'work_item_failed_transient'
          )
        LIMIT 1
        """
    )
    return session.execute(sql, {"id": work_item_id}).first() is not None


def _park_contract_error(
    session: Any,
    work_item_id: str,
    entity_ref_type: str,
    entity_ref_id: str,
    stage: str,
    error_detail: str,
) -> None:
    _set_work_item_stage(session, work_item_id, "parked:contract_error")
    evt = build_terminal_event(
        module=MODULE,
        work_item_id=work_item_id,
        entity_ref_type=entity_ref_type,
        entity_ref_id=entity_ref_id,
        stage="parked:contract_error",
        event_type="work_item_failed_contract",
        outcome="failed_contract",
        error_code="contract_error",
        counters={},
        refs={"error": error_detail[:200]},
    )
    emit(session, evt)
    session.commit()


# ---------------------------------------------------------------------------
# Handler entry point
# ---------------------------------------------------------------------------


def handle_account_discovery(work_item: Any) -> None:
    """
    RQ handler for the account_discovery stage.

    Args:
        work_item: dict with at minimum {"work_item_id": str, "stage": str}
                   as passed by run_worker.process_work_item().
    """
    work_item_id: str = (
        work_item["work_item_id"] if isinstance(work_item, dict) else str(work_item)
    )

    db_url = os.getenv("DATABASE_URL", "")
    engine = create_engine(_sa_url(db_url))

    try:
        with Session(engine) as session:
            # --- Load WorkItem ---
            try:
                wi = _load_work_item(session, work_item_id)
            except ValueError as exc:
                # WorkItem row missing — nothing to park; just propagate
                raise RuntimeError(f"WorkItem load failed: {exc}") from exc

            entity_ref_type = wi["entity_ref_type"]
            entity_ref_id = wi["entity_ref_id"]
            stage = wi["stage"]
            payload_data = (wi["payload_json"] or {}).get("data", {})
            query_object_id = payload_data.get("query_object_id")
            run_limits = resolve_run_limits(payload_data.get("run_limits_override"))

            # --- Idempotent replay guard: no-op without spending budget ---
            if _has_terminal_event(session, work_item_id):
                noop_evt = build_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage=stage,
                    event_type="handler_noop_idempotent",
                    outcome="noop",
                    refs={"reason": "terminal_event_already_present"},
                )
                emit(session, noop_evt)
                session.commit()
                return

            # --- Emit handler_started ---
            started_evt = build_handler_started(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                refs={"query_object_id": query_object_id or ""},
            )
            emit(session, started_evt)
            session.commit()

            # --- Contract preconditions ---
            if not query_object_id:
                _park_contract_error(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    "payload.data.query_object_id is required",
                )
                return

            # --- Select adapter (PH-EPIC-E-001: defaults to dummy_predictable) ---
            adapter_name = payload_data.get("adapter_plan")
            try:
                adapter = get_adapter(adapter_name)
            except ValueError as exc:
                _park_contract_error(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    str(exc),
                )
                return

            # --- Budget check and spend ---
            try:
                # Run cap guard before any budget-spending source attempt.
                queries_used = int(payload_data.get("queries_used", 1))
                external_calls_used = int(payload_data.get("external_calls_used", 0))
                pre_stop = evaluate_stop_rule(
                    limits=run_limits,
                    elapsed_seconds=0.0,
                    external_calls_used=external_calls_used,
                    queries_used=queries_used,
                    accounts_created_this_query=0,
                )
                if pre_stop == "budget_exhausted":
                    raise BudgetExhaustedError(wi["attempt_budget_remaining"])

                if should_decrement_budget(AttemptType.SOURCE_CALL.value):
                    check_budget(wi["attempt_budget_remaining"])
                    spend_result = spend_budget(
                        wi["attempt_budget_remaining"], AttemptType.SOURCE_CALL
                    )
                else:
                    spend_result = None
            except BudgetExhaustedError:
                _set_work_item_stage(session, work_item_id, "parked:budget_exhausted")
                evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage="parked:budget_exhausted",
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="budget_exhausted",
                    counters={},
                    refs={},
                )
                emit(session, evt)
                session.commit()
                return

            # Persist updated budget
            if spend_result is not None:
                session.execute(
                    text(
                        "UPDATE work_items SET attempt_budget_remaining = :r"
                        " WHERE work_item_id = :id"
                    ),
                    {"r": spend_result.remaining_after, "id": work_item_id},
                )
                session.commit()

            # --- Run discovery service ---
            limits: dict = {
                "max_accounts_per_run": run_limits.max_accounts_per_run,
                "max_external_calls_per_run": run_limits.max_external_calls_per_run,
                "max_runtime_seconds_per_run": run_limits.max_runtime_seconds_per_run,
                "max_queries_per_run": run_limits.max_queries_per_run,
                "max_accounts_per_query_object": run_limits.max_accounts_per_query_object,
                "timeout_seconds": run_limits.timeout_seconds,
            }
            context: dict = {
                "policy_pack_id": wi["trace_policy_pack_id"],
                "run_id": wi["trace_run_id"],
                "trace_correlation_id": wi["trace_correlation_id"],
            }

            try:
                svc_result = run_account_discovery(
                    session=session,
                    query_object_id=query_object_id,
                    adapter=adapter,
                    limits=limits,
                    context=context,
                    parent_work_item=wi,
                )
            except ValueError as exc:
                _park_contract_error(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    str(exc),
                )
                return
            except Exception as exc:
                policy = resolve_retry_policy()
                refs = {
                    "error": str(exc)[:200],
                    "retry_count_transient": policy.retry_count_transient,
                    "backoff_seconds": list(policy.backoff_seconds),
                }
                _set_work_item_stage(session, work_item_id, "parked:transient_error")
                evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage="parked:transient_error",
                    event_type="work_item_failed_transient",
                    outcome="failed_transient",
                    error_code="transient_error",
                    counters={},
                    refs=refs,
                )
                emit(session, evt)
                session.commit()
                return

            session.commit()

            # --- Terminal event ---
            if svc_result.stop_reason in {"budget_exhausted", "max_accounts_reached"}:
                _set_work_item_stage(session, work_item_id, "parked:budget_exhausted")
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage="parked:budget_exhausted",
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="budget_exhausted",
                    counters={"accounts_created": svc_result.accounts_created},
                    refs={"query_object_id": query_object_id},
                )
            elif svc_result.no_signal or svc_result.stop_reason == "no_signal":
                _set_work_item_stage(session, work_item_id, "parked:no_signal")
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage="parked:no_signal",
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="no_signal",
                    counters={"accounts_created": svc_result.accounts_created},
                    refs={"query_object_id": query_object_id},
                )
            else:
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage=stage,
                    event_type="work_item_completed",
                    outcome="ok",
                    counters={
                        "accounts_created": svc_result.accounts_created,
                        "accounts_updated": svc_result.accounts_updated,
                        "evidence_created": svc_result.evidence_created,
                        "downstream_enqueued": svc_result.downstream_enqueued,
                    },
                    refs={"query_object_id": query_object_id},
                )
            emit(session, terminal_evt)
            session.commit()

    finally:
        engine.dispose()
