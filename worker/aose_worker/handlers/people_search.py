"""
People search handler for the AOSE worker pipeline.

Registered in HANDLER_REGISTRY for stage 'people_search'.

Orchestration sequence:
  1. Load WorkItem from DB.
  2. Emit handler_started structured event.
  3. Validate payload preconditions (contract error → park immediately).
  4. Select adapter via registry (PH-EPIC-G-001 default: dummy_predictable_people).
  5. Enforce attempt budget before source call.
  6. Spend budget and persist updated remaining to DB.
  7. Call people search service.
  8. Commit canonical writes.
  9. Emit terminal structured event (completed / parked:no_signal / parked:needs_human).

Error routing (CONTRACT.yaml errors_and_routing):
  - missing account_id                     → parked:contract_error (no retry)
  - Account not found                      → parked:needs_human (no retry)
  - invalid adapter result                 → parked:contract_error (no retry)
  - budget_exhausted                       → parked:budget_exhausted (no retry)
  - no surviving contacts                  → parked:no_signal
  - needs_human (role ambiguity)           → parked:needs_human
  - transient failures                     → caller (RQ) retries while budget > 0
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.adapters.people_search.registry import get_adapter
from aose_worker.budget import (
    AttemptType,
    BudgetExhaustedError,
    check_budget,
    spend_budget,
)
from aose_worker.events import build_handler_started, build_terminal_event, emit
from aose_worker.services.people_search_service import run_people_search

MODULE = "aose_worker.handlers.people_search"


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


def _park(
    session: Any,
    work_item_id: str,
    entity_ref_type: str,
    entity_ref_id: str,
    stage: str,
    event_type: str,
    outcome: str,
    error_code: str | None,
    counters: dict,
    refs: dict,
) -> None:
    evt = build_terminal_event(
        module=MODULE,
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
    emit(session, evt)
    session.commit()


# ---------------------------------------------------------------------------
# Handler entry point
# ---------------------------------------------------------------------------


def handle_people_search(work_item: Any) -> None:
    """
    RQ handler for the people_search stage.

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
                raise RuntimeError(f"WorkItem load failed: {exc}") from exc

            entity_ref_type = wi["entity_ref_type"]
            entity_ref_id = wi["entity_ref_id"]
            stage = wi["stage"]
            payload_data = (wi["payload_json"] or {}).get("data", {})
            account_id = payload_data.get("account_id")
            role_targets = payload_data.get("role_targets")
            adapter_plan = payload_data.get("adapter_plan")

            # --- Emit handler_started ---
            started_evt = build_handler_started(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                refs={"account_id": account_id or ""},
            )
            emit(session, started_evt)
            session.commit()

            # --- Contract preconditions ---
            if not account_id:
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_failed_contract",
                    outcome="failed_contract",
                    error_code="contract_error",
                    counters={},
                    refs={"error": "payload.data.account_id is required"},
                )
                return

            # --- Select adapter (PH-EPIC-G-001: defaults to dummy_predictable_people) ---
            try:
                adapter = get_adapter(adapter_plan)
            except ValueError as exc:
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_failed_contract",
                    outcome="failed_contract",
                    error_code="contract_error",
                    counters={},
                    refs={"error": str(exc)[:200]},
                )
                return

            # --- Budget check and spend ---
            try:
                check_budget(wi["attempt_budget_remaining"])
                spend_result = spend_budget(
                    wi["attempt_budget_remaining"], AttemptType.SOURCE_CALL
                )
            except BudgetExhaustedError:
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="budget_exhausted",
                    counters={},
                    refs={},
                )
                return

            # Persist updated budget
            session.execute(
                text(
                    "UPDATE work_items SET attempt_budget_remaining = :r"
                    " WHERE work_item_id = :id"
                ),
                {"r": spend_result.remaining_after, "id": work_item_id},
            )
            session.commit()

            # --- Run people search service ---
            limits: dict = {
                "max_contacts_per_account": 3,  # CONTRACT.yaml caps.max_contacts_per_account
            }
            context: dict = {
                "policy_pack_id": wi["trace_policy_pack_id"],
                "run_id": wi["trace_run_id"],
                "trace_correlation_id": wi["trace_correlation_id"],
            }

            try:
                svc_result = run_people_search(
                    session=session,
                    account_id=account_id,
                    adapter=adapter,
                    role_targets=role_targets,
                    limits=limits,
                    context=context,
                    parent_work_item=wi,
                )
            except ValueError as exc:
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_failed_contract",
                    outcome="failed_contract",
                    error_code="contract_error",
                    counters={},
                    refs={"error": str(exc)[:200]},
                )
                return

            session.commit()

            # --- Terminal event ---
            counters = {
                "contacts_created": svc_result.contacts_created,
                "downstream_enqueued": svc_result.downstream_enqueued,
            }
            refs = {"account_id": account_id}

            if svc_result.run_cap_exhausted:
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage=stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="budget_exhausted",
                    counters=counters,
                    refs=refs,
                )
            elif svc_result.needs_human:
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage=stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="needs_human",
                    counters=counters,
                    refs=refs,
                )
            elif svc_result.no_signal:
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage=stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="no_signal",
                    counters=counters,
                    refs=refs,
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
                    counters=counters,
                    refs=refs,
                )
            emit(session, terminal_evt)
            session.commit()

    finally:
        engine.dispose()
