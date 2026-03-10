"""
Contact enrichment handler for the AOSE worker pipeline.

Registered in HANDLER_REGISTRY for stage 'contact_enrichment'.

Orchestration sequence:
  1. Load WorkItem from DB.
  2. Emit handler_started structured event.
  3. Validate payload preconditions (missing contact_id → park immediately).
  4. Enforce attempt budget before DNS source call.
  5. Spend budget and persist updated remaining to DB.
  6. Call contact enrichment service (may raise TransientDnsError → propagates).
  7. Commit canonical writes.
  8. Emit terminal structured event.

Error routing (CONTRACT.yaml routing_rules):
  - missing contact_id             → parked:contract_error (no retry)
  - Contact not found              → parked:contract_error (no retry)
  - budget_exhausted               → parked:budget_exhausted (no retry)
  - TransientDnsError              → propagates; RQ retries while budget > 0
  - route == no_signal             → parked:no_signal
  - route == policy_blocked        → parked:policy_blocked
  - route == needs_human           → parked:needs_human
  - route == copy_generate         → work_item_completed
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.budget import (
    AttemptType,
    BudgetExhaustedError,
    check_budget,
    spend_budget,
)
from aose_worker.events import build_handler_started, build_terminal_event, emit
from aose_worker.services.contact_enrichment_service import (
    ROUTE_BUDGET_EXHAUSTED,
    ROUTE_COPY_GENERATE,
    ROUTE_NEEDS_HUMAN,
    ROUTE_POLICY_BLOCKED,
    run_contact_enrichment,
)

MODULE = "aose_worker.handlers.contact_enrichment"


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


def handle_contact_enrichment(work_item: Any) -> None:
    """
    RQ handler for the contact_enrichment stage.

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
            contact_id = payload_data.get("contact_id")

            # --- Emit handler_started ---
            started_evt = build_handler_started(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                refs={"contact_id": contact_id or ""},
            )
            emit(session, started_evt)
            session.commit()

            # --- Contract preconditions ---
            if not contact_id:
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
                    refs={"error": "payload.data.contact_id is required"},
                )
                return

            # --- Budget check and spend (DNS is a source call) ---
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
                    refs={"contact_id": contact_id},
                )
                return

            # Persist updated budget before making the DNS call
            session.execute(
                text(
                    "UPDATE work_items SET attempt_budget_remaining = :r"
                    " WHERE work_item_id = :id"
                ),
                {"r": spend_result.remaining_after, "id": work_item_id},
            )
            session.commit()

            # --- Run enrichment service ---
            # TransientDnsError propagates out — RQ retries while budget > 0.
            try:
                svc_result = run_contact_enrichment(
                    session=session,
                    contact_id=contact_id,
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
                "channel_updated": int(svc_result.channel_updated),
                "copy_generate_enqueued": int(svc_result.copy_generate_enqueued),
            }
            # refs must never contain raw email (PII) — contact_id only
            refs = {"contact_id": contact_id}

            route = svc_result.route

            if route == ROUTE_BUDGET_EXHAUSTED:
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
            elif route == ROUTE_COPY_GENERATE:
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
            elif route == ROUTE_POLICY_BLOCKED:
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage=stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="policy_blocked",
                    counters=counters,
                    refs=refs,
                )
            elif route == ROUTE_NEEDS_HUMAN:
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
            else:
                # ROUTE_NO_SIGNAL (default fallback)
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

            emit(session, terminal_evt)
            session.commit()

    finally:
        engine.dispose()
