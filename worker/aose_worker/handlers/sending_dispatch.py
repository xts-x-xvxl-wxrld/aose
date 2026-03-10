"""
Sending dispatch handler for the AOSE worker pipeline.

Registered in HANDLER_REGISTRY for stage 'sending_dispatch'.

Spec I1 implementation:
  - Consume sending_dispatch WorkItems (SPEC-I1).
  - Validate payload version 1 with required fields draft_id and decision_id.
  - Load OutreachDraft, ApprovalDecision, Contact, and Account.
  - Enforce the Epic I approval contract:
      - status must be 'approved'
      - policy_pack_id must be 'safe_v0_1'
      - required fields decision_key, reviewer_id, reviewer_role, policy_pack_id must be present
  - Evaluate gates in CONTRACT-locked order (see GATE_ORDER below).
  - Under safe_v0_1: send_enabled=false is the locked default.
    When disabled, park safely and do not create a SendAttempt.
  - Provider stub references PH-001; no external send side effects.
  - Emit redacted structured events only (no full email/phone/message body).

Gate order (CONTRACT-locked):
  HardSafetyGate -> BudgetGate -> DataQualityGate -> EvidenceGate ->
  FitScoreGate -> ContactabilityGate -> DraftClaimEvidenceGate -> SendGate

Locked defaults (safe_v0_1):
  - send_enabled: false
  - send_provider_enum: SEND_SRC_01 (PH-001)
  - send_mode: sandbox_log_sink_only
  - external_send_side_effects: forbidden

Orchestration sequence:
  1. Load WorkItem from DB.
  2. Emit handler_started structured event.
  3. Validate payload_version == 1; contract_error if not.
  4. Validate draft_id and decision_id present; contract_error if missing.
  5. Load OutreachDraft; contract_error if not found.
  6. Load ApprovalDecision; contract_error if not found.
  7. Enforce approval contract (status=approved, policy_pack_id=safe_v0_1,
     required fields present); park policy_blocked or contract_error.
  8. Load Contact (via draft.contact_id); contract_error if not found.
  9. Load Account (via draft.account_id); contract_error if not found.
 10. Evaluate gates in locked order; park on first FAIL.
 11. If SendGate FAIL (send_enabled=false): park policy_blocked, no SendAttempt.
 12. If all gates PASS (send_enabled=true, currently impossible in safe_v0_1):
     create or reuse SendAttempt; emit work_item_completed.

Error routing:
  - unsupported payload_version                         -> work_item_failed_contract / contract_error
  - missing draft_id or decision_id                     -> work_item_failed_contract / contract_error
  - draft not found                                     -> work_item_failed_contract / contract_error
  - approval decision not found                         -> work_item_failed_contract / contract_error
  - required approval fields missing                    -> work_item_failed_contract / contract_error
  - approval status != approved                         -> work_item_parked / policy_blocked
  - approval policy_pack_id != safe_v0_1                -> work_item_parked / policy_blocked
  - contact not found                                   -> work_item_failed_contract / contract_error
  - account not found                                   -> work_item_failed_contract / contract_error
  - BudgetGate FAIL                                     -> work_item_parked / budget_exhausted
  - gate FAIL (non-budget)                              -> work_item_parked / policy_blocked
  - SendGate FAIL (send_enabled=false)                  -> work_item_parked / policy_blocked
  - transient DB error                                  -> propagates; RQ retries
"""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.events import (
    build_event,
    build_handler_started,
    build_terminal_event,
    emit,
)
from aose_worker.services.send_policy_service import evaluate_send_policy
from aose_worker.services.sandbox_sender_service import (
    LOCKED_PROVIDER,
    build_sandbox_sink_refs,
    create_or_reuse_send_attempt,
    get_existing_send_attempt,
)

MODULE = "aose_worker.handlers.sending_dispatch"

_POLICY_PACK_ID_REQUIRED = "safe_v0_1"
_STATUS_REQUIRED = "approved"

# Required approval fields per Epic I contract
_REQUIRED_APPROVAL_FIELDS = (
    "decision_key",
    "reviewer_id",
    "reviewer_role",
    "policy_pack_id",
)


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
        "SELECT draft_id, contact_id, account_id, channel, subject, body "
        "FROM outreach_drafts WHERE draft_id = :did"
    )
    row = session.execute(sql, {"did": draft_id}).mappings().first()
    return dict(row) if row else None


def _load_approval_decision(session: Any, decision_id: str) -> dict[str, Any] | None:
    sql = text(
        """
        SELECT decision_id, draft_id, contact_id, status, policy_pack_id,
               decision_key, reviewer_id, reviewer_role, overridden_gates_json
        FROM approval_decisions
        WHERE decision_id = :did
        """
    )
    row = session.execute(sql, {"did": decision_id}).mappings().first()
    return dict(row) if row else None


def _load_contact(session: Any, contact_id: str) -> dict[str, Any] | None:
    sql = text(
        "SELECT contact_id, account_id, channels_json, status "
        "FROM contacts WHERE contact_id = :cid"
    )
    row = session.execute(sql, {"cid": contact_id}).mappings().first()
    return dict(row) if row else None


def _load_account(session: Any, account_id: str) -> dict[str, Any] | None:
    sql = text("SELECT account_id, status FROM accounts WHERE account_id = :aid")
    row = session.execute(sql, {"aid": account_id}).mappings().first()
    return dict(row) if row else None


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
# Gate evaluation (CONTRACT-locked order)
# ---------------------------------------------------------------------------


def _evaluate_gates(
    *,
    attempt_budget_remaining: int,
    send_enabled: bool,
) -> tuple[bool, str]:
    """
    Evaluate send eligibility gates in CONTRACT-locked order.

    Gate stubs 1, 3–5, 7 always PASS in the safe_v0_1 skeleton (PH-EPIC-I-001).
    Gate 2 (BudgetGate) checks attempt budget.
    Gate 6 (ContactabilityGate) always PASS in skeleton (PH-EPIC-I-001).
    Gate 8 (SendGate) enforces send_enabled; locked false in safe_v0_1.

    Returns (passed, blocking_gate_name).
    If all gates pass, returns (True, "").
    If any gate fails, returns (False, <gate_name>).
    """
    # 1. HardSafetyGate — skeleton PASS (PH-EPIC-I-001)

    # 2. BudgetGate — park if budget exhausted
    if attempt_budget_remaining <= 0:
        return False, "BudgetGate"

    # 3. DataQualityGate — skeleton PASS (PH-EPIC-I-001)

    # 4. EvidenceGate — skeleton PASS (PH-EPIC-I-001)

    # 5. FitScoreGate — skeleton PASS (PH-EPIC-I-001)

    # 6. ContactabilityGate — skeleton PASS (PH-EPIC-I-001)

    # 7. DraftClaimEvidenceGate — skeleton PASS (PH-EPIC-I-001)

    # 8. SendGate — fail-closed when send_enabled=false (locked default in safe_v0_1)
    if not send_enabled:
        return False, "SendGate"

    return True, ""


# ---------------------------------------------------------------------------
# Handler entry point
# ---------------------------------------------------------------------------


def handle_sending_dispatch(work_item: Any) -> None:
    """
    RQ handler for the sending_dispatch stage.

    Args:
        work_item: dict with at minimum {"work_item_id": str} as passed by
                   run_worker.process_work_item().
    """
    work_item_id: str = (
        work_item["work_item_id"] if isinstance(work_item, dict) else str(work_item)
    )

    # Read send_enabled at call time so env can be patched in tests if needed.
    send_enabled = os.getenv("SEND_ENABLED", "false").lower() == "true"

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
            payload_json = wi["payload_json"] or {}
            payload_version = payload_json.get("v", 1)
            payload_data = payload_json.get("data", {})
            attempt_budget_remaining = wi.get("attempt_budget_remaining") or 0

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

            # --- Validate required payload fields ---
            draft_id = payload_data.get("draft_id")
            decision_id = payload_data.get("decision_id")

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

            if not decision_id:
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
                    refs={"error": "missing required field: decision_id"},
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
                    refs={"error": "draft_not_found"},
                )
                return

            # --- Load ApprovalDecision ---
            approval = _load_approval_decision(session, decision_id)
            if approval is None:
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
                    refs={"error": "approval_decision_not_found"},
                )
                return

            # --- Enforce approval linkage: decision must target this draft ---
            if approval.get("draft_id") != draft_id:
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
                    refs={"reason": "approval_draft_id_mismatch"},
                )
                return

            # --- Enforce approval contract: required fields ---
            for field in _REQUIRED_APPROVAL_FIELDS:
                if not approval.get(field):
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
                        refs={"error": f"approval missing required field: {field}"},
                    )
                    return

            # --- Enforce approval contract: no STOP-gate override behavior ---
            # Any override payload is fail-closed in the I1 skeleton.
            if approval.get("overridden_gates_json"):
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="policy_blocked",
                    counters={},
                    refs={"reason": "gate_overrides_not_allowed"},
                )
                return

            # --- Enforce approval contract: status must be 'approved' ---
            if approval["status"] != _STATUS_REQUIRED:
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="policy_blocked",
                    counters={},
                    refs={
                        "reason": f"approval_status_not_approved: {approval['status']}"
                    },
                )
                return

            # --- Enforce approval contract: policy_pack_id must be 'safe_v0_1' ---
            if approval["policy_pack_id"] != _POLICY_PACK_ID_REQUIRED:
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="policy_blocked",
                    counters={},
                    refs={
                        "reason": f"policy_pack_id_mismatch: {approval['policy_pack_id']}"
                    },
                )
                return

            # --- Load Contact ---
            contact_id = draft["contact_id"]
            contact = _load_contact(session, contact_id)
            if contact is None:
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
                    refs={"error": "contact_not_found"},
                )
                return

            # --- Enforce linked canonical records ---
            if approval.get("contact_id") != contact_id:
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
                    refs={"reason": "approval_contact_id_mismatch"},
                )
                return

            # --- Load Account ---
            account_id = draft["account_id"]
            account = _load_account(session, account_id)
            if account is None:
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
                    refs={"error": "account_not_found"},
                )
                return

            if contact.get("account_id") != account_id:
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
                    refs={"reason": "contact_account_id_mismatch"},
                )
                return

            # --- Evaluate base gates (CONTRACT-locked order) ---
            gates_passed, blocking_gate = _evaluate_gates(
                attempt_budget_remaining=attempt_budget_remaining,
                send_enabled=send_enabled,
            )

            if not gates_passed:
                if blocking_gate == "BudgetGate":
                    error_code = "budget_exhausted"
                else:
                    error_code = "policy_blocked"

                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code=error_code,
                    counters={},
                    refs={"blocking_gate": blocking_gate},
                )
                return

            # --- Evaluate I3 send policy and compliance layer ---
            channel = draft.get("channel", "email")
            existing_attempt = get_existing_send_attempt(
                session=session,
                draft_id=draft_id,
                channel=channel,
            )
            policy_decision = evaluate_send_policy(
                session=session,
                draft=draft,
                contact=contact,
                account=account,
                send_enabled=send_enabled,
                replay_existing=existing_attempt is not None,
            )
            if policy_decision.outcome == "STOP":
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="policy_blocked",
                    counters={},
                    refs={
                        "blocking_gate": policy_decision.gate,
                        "reason": policy_decision.reason,
                    },
                )
                return
            if policy_decision.outcome == "REVIEW":
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
                    refs={
                        "blocking_gate": policy_decision.gate,
                        "reason": policy_decision.reason,
                    },
                )
                return

            # --- All gates PASS: create/reuse SendAttempt + sandbox sink (I2) ---
            send_attempt = create_or_reuse_send_attempt(
                session=session,
                draft_id=draft_id,
                decision_id=decision_id,
                channel=channel,
            )
            sink_refs = build_sandbox_sink_refs(
                session=session,
                draft=draft,
                contact=contact,
                send_attempt=send_attempt,
            )

            sink_evt = build_event(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                event_type="handler_succeeded",
                outcome="ok",
                counters={
                    "send_attempt_reused": 1 if send_attempt.reused else 0,
                    "claim_hash_count": len(sink_refs.get("claim_hashes", [])),
                    "evidence_ref_count": len(sink_refs.get("evidence_ids", [])),
                },
                refs=sink_refs,
            )
            emit(session, sink_evt)
            session.commit()

            terminal_evt = build_terminal_event(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                event_type="work_item_completed",
                outcome="ok",
                counters={},
                refs={"channel": channel, "provider_id": LOCKED_PROVIDER},
            )
            emit(session, terminal_evt)
            session.commit()

    finally:
        engine.dispose()
