"""
Approval request handler for the AOSE worker pipeline.

Registered in HANDLER_REGISTRY for stage 'approval_request'.

Epic H3 implementation:
  - Consume approval_request WorkItems (SPEC-H3).
  - Record ApprovalDecision as an explicit canonical record.
  - Validate reviewer authority against canonical roles.
  - Enforce deterministic decision_key / decision_id behaviour.
  - Route deterministically by decision status.

Orchestration sequence:
  1. Load WorkItem from DB.
  2. Emit handler_started structured event.
  3. Validate payload_version == 1 and draft_id present.
  4. Load OutreachDraft; resolve contact_id.
  5. Check if decision data (status, reviewer_id, reviewer_role) is present.
     - If absent: park as needs_human (initial enqueue from copy_generate awaiting review).
  6. Validate reviewer_role authority → park contract_error if viewer.
  7. Validate status is a locked value → park contract_error if invalid.
  8. Compute decision_key from work_item_id, contact_id, action_type, policy_pack_id, draft_id.
  9. Lookup existing decision_key (replay path: reuse existing decision_id).
  10. Persist ApprovalDecision (ON CONFLICT DO NOTHING).
  11. Commit ApprovalDecision.
  12. Enqueue next-stage WorkItem by routing status.
  13. Emit approval_recorded.
  14. Emit work_item_completed (approved) or work_item_parked (all other statuses).
  15. Commit.

Error routing:
  - missing draft_id / draft not found / unsupported payload_version → parked:contract_error
  - viewer attempted approval                                          → parked:contract_error
  - invalid status value                                               → parked:contract_error
  - no decision data in payload (initial enqueue)                     → parked:needs_human
  - transient DB error                                                 → propagates; RQ retries
"""

from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import (
    make_decision_id,
    make_decision_key,
    make_dispatch_idempotency_key,
    make_work_item_id,
)
from aose_worker.events import (
    build_event,
    build_handler_started,
    build_terminal_event,
    emit,
)
from aose_worker.services.approval_decision_service import (
    ACTION_TYPE_DEFAULT,
    AuthorityError,
    InvalidStatusError,
    check_authority,
    check_status,
    get_next_stage,
    lookup_decision_by_key,
    persist_decision,
)

MODULE = "aose_worker.handlers.approval_request"


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


def _load_draft(session: Any, draft_id: str) -> dict[str, Any] | None:
    sql = text(
        "SELECT draft_id, contact_id, account_id FROM outreach_drafts WHERE draft_id = :did"
    )
    row = session.execute(sql, {"did": draft_id}).mappings().first()
    return dict(row) if row else None


def _enqueue_next_stage(
    session: Any,
    *,
    stage: str,
    draft_id: str,
    decision_id: str,
    parent_work_item: dict[str, Any],
) -> bool:
    """Enqueue next-stage WorkItem. Returns True if newly inserted."""
    idempotency_key = make_dispatch_idempotency_key(draft_id, decision_id)
    new_work_item_id = make_work_item_id()
    payload = {
        "v": 1,
        "data": {"draft_id": draft_id, "decision_id": decision_id},
    }
    sql = text(
        """
        INSERT INTO work_items (
            work_item_id, entity_ref_type, entity_ref_id, stage,
            payload_json, payload_version,
            attempt_budget_remaining, attempt_budget_policy,
            idempotency_key,
            trace_run_id, trace_parent_work_item_id,
            trace_correlation_id, trace_policy_pack_id,
            created_at
        ) VALUES (
            :work_item_id, :entity_ref_type, :entity_ref_id, :stage,
            CAST(:payload AS JSONB), 1,
            :attempt_budget_remaining, :attempt_budget_policy,
            :idempotency_key,
            :trace_run_id, :trace_parent_work_item_id,
            :trace_correlation_id, :trace_policy_pack_id,
            now()
        ) ON CONFLICT (idempotency_key) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "work_item_id": new_work_item_id,
            "entity_ref_type": parent_work_item.get("entity_ref_type", "contact"),
            "entity_ref_id": parent_work_item.get("entity_ref_id", ""),
            "stage": stage,
            "payload": json.dumps(payload),
            "attempt_budget_remaining": parent_work_item.get(
                "attempt_budget_remaining", 3
            ),
            "attempt_budget_policy": parent_work_item.get(
                "attempt_budget_policy", "standard"
            ),
            "idempotency_key": idempotency_key,
            "trace_run_id": parent_work_item.get("trace_run_id", ""),
            "trace_parent_work_item_id": parent_work_item.get("work_item_id"),
            "trace_correlation_id": parent_work_item.get("trace_correlation_id", ""),
            "trace_policy_pack_id": parent_work_item.get(
                "trace_policy_pack_id", "safe_v0_1"
            ),
        },
    )
    return result.rowcount > 0


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


def handle_approval_request(work_item: Any) -> None:
    """
    RQ handler for the approval_request stage.

    Args:
        work_item: dict with at minimum {"work_item_id": str} as passed by
                   run_worker.process_work_item().
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
            policy_pack_id = wi.get("trace_policy_pack_id") or "safe_v0_1"
            payload_json = wi["payload_json"] or {}
            payload_version = payload_json.get("v", 1)
            payload_data = payload_json.get("data", {})

            # --- Emit handler_started ---
            started_evt = build_handler_started(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                refs={},
            )
            emit(session, started_evt)
            session.commit()

            # --- Validate payload_version ---
            if payload_version != 1:
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
                    refs={"error": f"unsupported payload_version: {payload_version}"},
                )
                return

            # --- Validate draft_id ---
            draft_id = payload_data.get("draft_id")
            if not draft_id:
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
                    refs={"error": "missing required field: draft_id"},
                )
                return

            # --- Load OutreachDraft ---
            draft = _load_draft(session, draft_id)
            if draft is None:
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
                    refs={"error": f"draft not found: {draft_id!r}"},
                )
                return

            contact_id = draft["contact_id"]

            # --- Check if decision data is present ---
            status = payload_data.get("status")
            reviewer_id = payload_data.get("reviewer_id")
            reviewer_role = payload_data.get("reviewer_role")

            if not status or not reviewer_id or not reviewer_role:
                # Initial enqueue from copy_generate: no decision yet.
                # Park awaiting human review (routes to review lane).
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="needs_human",
                    counters={},
                    refs={"draft_id": draft_id},
                )
                return

            # --- Validate reviewer authority ---
            try:
                check_authority(reviewer_role)
            except AuthorityError as exc:
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
                    refs={"error": str(exc)[:200], "draft_id": draft_id},
                )
                return

            # --- Validate status ---
            try:
                check_status(status)
            except InvalidStatusError as exc:
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
                    refs={"error": str(exc)[:200], "draft_id": draft_id},
                )
                return

            # --- Compute decision_key / decision_id ---
            action_type = payload_data.get("action_type") or ACTION_TYPE_DEFAULT
            notes = payload_data.get("notes")
            overridden_gates = payload_data.get("overridden_gates") or []

            dk = make_decision_key(
                work_item_id=work_item_id,
                contact_id=contact_id,
                action_type=action_type,
                policy_pack_id=policy_pack_id,
                draft_id=draft_id,
            )
            decision_id = make_decision_id(draft_id=draft_id, decision_key=dk)

            # --- Replay: reuse existing decision_id if key already exists ---
            existing_id = lookup_decision_by_key(session, dk)
            if existing_id:
                decision_id = existing_id

            # --- Persist ApprovalDecision (commit before enqueue) ---
            persist_decision(
                session,
                decision_id=decision_id,
                decision_key=dk,
                draft_id=draft_id,
                work_item_id=work_item_id,
                contact_id=contact_id,
                action_type=action_type,
                status=status,
                reviewer_id=reviewer_id,
                reviewer_role=reviewer_role,
                policy_pack_id=policy_pack_id,
                notes=notes,
                overridden_gates=overridden_gates,
            )
            session.commit()

            # --- Route and enqueue next-stage WorkItem ---
            next_stage = get_next_stage(status)
            _enqueue_next_stage(
                session,
                stage=next_stage,
                draft_id=draft_id,
                decision_id=decision_id,
                parent_work_item=wi,
            )
            session.commit()

            # --- Emit approval_recorded ---
            approval_evt = build_event(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                event_type="approval_recorded",
                outcome="ok",
                counters={},
                refs={"draft_id": draft_id},
            )
            emit(session, approval_evt)

            # --- Terminal event ---
            if status == "approved":
                terminal_event_type = "work_item_completed"
                terminal_outcome = "ok"
            else:
                terminal_event_type = "work_item_parked"
                terminal_outcome = "parked"

            terminal_evt = build_terminal_event(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                event_type=terminal_event_type,
                outcome=terminal_outcome,
                counters={},
                refs={"draft_id": draft_id},
            )
            emit(session, terminal_evt)
            session.commit()

    finally:
        engine.dispose()
