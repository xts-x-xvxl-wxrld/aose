"""
Copy generate handler for the AOSE worker pipeline.

Registered in HANDLER_REGISTRY for stage 'copy_generate'.

Epic H1 + H2 implementation:
  H1 — Build evidence digest from canonical records.
  H2 — Generate template-based OutreachDraft + PersonalizationAnchors,
       persist idempotently, enqueue approval_request.

Orchestration sequence:
  1. Load WorkItem from DB.
  2. Emit handler_started structured event.
  3. Validate required payload fields (seller_id, account_id, contact_id, evidence_ids).
  4. Build evidence digest (H1 — DB reads only, no budget spend).
  5. Emit evidence_digest_built.
  6. Check max_drafts_per_contact cap.
  7. Generate draft + anchors (H2 — template, no model call).
  8. Persist OutreachDraft + PersonalizationAnchors (ON CONFLICT DO NOTHING).
  9. Emit draft_generated or draft_flagged_for_review.
  10. Enqueue approval_request WorkItem (ON CONFLICT DO NOTHING).
  11. Emit work_item_completed.

Error routing (CONTRACT.yaml errors_and_parking):
  - missing required payload field            → parked:contract_error
  - missing canonical seller/account/contact  → parked:contract_error
  - missing evidence_id                       → parked:contract_error
  - max_drafts_per_contact cap hit            → parked:budget_exhausted
  - db timeout / transient error              → propagates; RQ retries while budget > 0
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.canonical_ids import (
    make_anchor_key,
    make_approval_request_idempotency_key,
    make_draft_id,
    make_work_item_id,
)
from aose_worker.events import (
    build_event,
    build_handler_started,
    build_terminal_event,
    emit,
)
from aose_worker.services.copy_generator_service import (
    MAX_DRAFTS_PER_CONTACT,
    GateOutcome,
    generate_draft_v0,
)
from aose_worker.services.evidence_digest_service import (
    DigestContractError,
    build_evidence_digest,
)

MODULE = "aose_worker.handlers.copy_generate"


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


def _count_drafts_for_contact(session: Any, contact_id: str) -> int:
    """Return number of existing drafts for this contact (cap enforcement)."""
    sql = text("SELECT COUNT(*) FROM outreach_drafts WHERE contact_id = :cid")
    row = session.execute(sql, {"cid": contact_id}).first()
    return int(row[0]) if row else 0


def _upsert_draft(
    session: Any,
    draft_id: str,
    contact_id: str,
    account_id: str,
    channel: str,
    language: str,
    policy_pack_id: str,
    subject: str,
    body: str,
    risk_flags: list,
) -> bool:
    """Insert OutreachDraft. Returns True if newly inserted."""
    sql = text(
        """
        INSERT INTO outreach_drafts (
            draft_id, contact_id, account_id, channel, language,
            policy_pack_id, subject, body, risk_flags_json, created_at, v
        ) VALUES (
            :draft_id, :contact_id, :account_id, :channel, :language,
            :policy_pack_id, :subject, :body, CAST(:risk_flags AS JSONB), :created_at, 1
        ) ON CONFLICT (draft_id) DO NOTHING
        """
    )
    result = session.execute(
        sql,
        {
            "draft_id": draft_id,
            "contact_id": contact_id,
            "account_id": account_id,
            "channel": channel,
            "language": language,
            "policy_pack_id": policy_pack_id,
            "subject": subject,
            "body": body,
            "risk_flags": json.dumps(risk_flags),
            "created_at": datetime.now(tz=timezone.utc),
        },
    )
    return result.rowcount > 0


def _upsert_anchors(
    session: Any,
    draft_id: str,
    anchors: list,
) -> int:
    """Insert PersonalizationAnchors. Returns count of newly inserted rows."""
    inserted = 0
    for anchor in anchors:
        anchor_key = make_anchor_key(draft_id, anchor.span, anchor.evidence_ids)
        sql = text(
            """
            INSERT INTO personalization_anchors (
                anchor_key, draft_id, span, evidence_ids_json, v
            ) VALUES (
                :anchor_key, :draft_id, :span, CAST(:eids AS JSONB), 1
            ) ON CONFLICT (anchor_key) DO NOTHING
            """
        )
        result = session.execute(
            sql,
            {
                "anchor_key": anchor_key,
                "draft_id": draft_id,
                "span": anchor.span,
                "eids": json.dumps(anchor.evidence_ids),
            },
        )
        inserted += result.rowcount
    return inserted


def _enqueue_approval_request(
    session: Any,
    draft_id: str,
    parent_work_item: dict[str, Any],
) -> bool:
    """
    Enqueue an approval_request WorkItem (idempotent via ON CONFLICT DO NOTHING).

    Returns True if newly inserted.
    """
    idempotency_key = make_approval_request_idempotency_key(draft_id)
    new_work_item_id = make_work_item_id()
    payload = {
        "v": 1,
        "data": {"draft_id": draft_id},
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
            :work_item_id, :entity_ref_type, :entity_ref_id, 'approval_request',
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


def handle_copy_generate(work_item: Any) -> None:
    """
    RQ handler for the copy_generate stage.

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

            contact_id_hint = payload_data.get("contact_id") or ""

            # --- Emit handler_started ---
            started_evt = build_handler_started(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                refs={"contact_id": contact_id_hint},
            )
            emit(session, started_evt)
            session.commit()

            # --- Validate required payload fields ---
            seller_id = payload_data.get("seller_id")
            account_id = payload_data.get("account_id")
            contact_id = payload_data.get("contact_id")
            evidence_ids = payload_data.get("evidence_ids")
            language = payload_data.get("language") or "en"
            channel = payload_data.get("channel") or "email"
            sequence_no = int(payload_data.get("sequence_no") or 1)
            variant_no = int(payload_data.get("variant_no") or 1)

            missing = [
                f
                for f, v in (
                    ("seller_id", seller_id),
                    ("account_id", account_id),
                    ("contact_id", contact_id),
                    ("evidence_ids", evidence_ids),
                )
                if not v
            ]
            if missing:
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
                    refs={"error": f"missing required fields: {missing}"},
                )
                return

            # --- H1: Build evidence digest (DB reads only) ---
            try:
                digest = build_evidence_digest(
                    session=session,
                    seller_id=seller_id,
                    account_id=account_id,
                    contact_id=contact_id,
                    evidence_ids=evidence_ids,
                    language=language,
                    channel=channel,
                )
            except DigestContractError as exc:
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

            # Emit evidence_digest_built (non-terminal informational event)
            digest_evt = build_event(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                event_type="evidence_digest_built",
                outcome="ok",
                counters={"evidence_item_count": len(digest.evidence_items)},
                refs={
                    "account_id": account_id,
                    "evidence_ids": evidence_ids,
                },
            )
            emit(session, digest_evt)
            session.commit()

            # --- H2: Cap check before generating draft ---
            draft_count = _count_drafts_for_contact(session, contact_id)
            if draft_count >= MAX_DRAFTS_PER_CONTACT:
                _park(
                    session,
                    work_item_id,
                    entity_ref_type,
                    entity_ref_id,
                    stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code="budget_exhausted",
                    counters={"existing_draft_count": draft_count},
                    refs={"account_id": account_id},
                )
                return

            # --- H2: Generate draft (template-based, no model call) ---
            gen_result = generate_draft_v0(digest)
            draft_spec = gen_result.draft

            # --- H2: Persist OutreachDraft + PersonalizationAnchors (idempotent) ---
            draft_id = make_draft_id(contact_id, sequence_no, variant_no)

            _upsert_draft(
                session,
                draft_id=draft_id,
                contact_id=contact_id,
                account_id=account_id,
                channel=channel,
                language=language,
                policy_pack_id=wi["trace_policy_pack_id"],
                subject=draft_spec.subject,
                body=draft_spec.body,
                risk_flags=draft_spec.risk_flags,
            )
            anchors_inserted = _upsert_anchors(session, draft_id, draft_spec.anchors)
            session.commit()

            # --- H2: Emit draft event ---
            draft_event_type = (
                "draft_generated"
                if gen_result.gate_outcome == GateOutcome.PASS
                else "draft_flagged_for_review"
            )
            draft_evt = build_event(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                event_type=draft_event_type,
                outcome="ok",
                counters={
                    "anchor_count": len(draft_spec.anchors),
                    "anchors_inserted": anchors_inserted,
                },
                refs={
                    "account_id": account_id,
                    "evidence_ids": evidence_ids,
                },
            )
            emit(session, draft_evt)

            # --- H2: Enqueue approval_request ---
            _enqueue_approval_request(session, draft_id, wi)
            session.commit()

            # --- Terminal event ---
            terminal_evt = build_terminal_event(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
                event_type="work_item_completed",
                outcome="ok",
                counters={
                    "evidence_item_count": len(digest.evidence_items),
                    "anchor_count": len(draft_spec.anchors),
                },
                refs={"account_id": account_id},
            )
            emit(session, terminal_evt)
            session.commit()

    finally:
        engine.dispose()
