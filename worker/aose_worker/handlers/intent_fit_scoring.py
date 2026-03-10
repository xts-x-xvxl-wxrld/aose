"""
Intent-fit scoring handler for Epic F1.

This handler implements deterministic scorecard upsert orchestration only.
Rule scoring and promotion lanes are handled in later Epic F specs.
"""

from __future__ import annotations

import json
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
from aose_worker.services.intent_fit_scoring_service import (
    ScoreValue,
    build_scorecard_upsert_input,
    resolve_evidence_category,
    validate_scoring_payload,
)
from aose_worker.canonical_ids import make_work_item_id
from aose_worker.services.fit_intent_rules import ScoringEvidence, score_fit_intent
from aose_worker.services.intent_fit_promotion import (
    GateOutcomes,
    budget_gate,
    data_quality_gate,
    evaluate_lane,
    evidence_gate,
    hard_safety_gate,
)

MODULE = "aose_worker.handlers.intent_fit_scoring"


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
    session.execute(
        text("UPDATE work_items SET stage = :stage WHERE work_item_id = :id"),
        {"stage": stage, "id": work_item_id},
    )


def _has_terminal_event(session: Any, work_item_id: str) -> bool:
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
    *,
    session: Any,
    work_item_id: str,
    entity_ref_type: str,
    entity_ref_id: str,
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


def _load_account(session: Any, account_id: str) -> dict[str, Any]:
    sql = text(
        """
        SELECT account_id, name, domain, country, status, provenance, evidence_ids
        FROM accounts
        WHERE account_id = :account_id
        """
    )
    row = session.execute(sql, {"account_id": account_id}).mappings().first()
    if row is None:
        raise ValueError(f"Account not found: {account_id!r}")
    d = dict(row)
    if not d.get("country") or d.get("status") not in {"candidate", "target"}:
        raise ValueError("Account missing required Epic F fields")
    return d


def _resolve_query_object_id_from_account_provenance(
    account: dict[str, Any],
) -> str | None:
    provenance = account.get("provenance")
    if isinstance(provenance, list):
        for entry in provenance:
            if isinstance(entry, dict) and isinstance(
                entry.get("query_object_id"), str
            ):
                return entry["query_object_id"]
    if isinstance(provenance, dict) and isinstance(
        provenance.get("query_object_id"), str
    ):
        return provenance["query_object_id"]
    return None


def _load_query_object(session: Any, query_object_id: str) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                """
            SELECT query_object_id, seller_id
            FROM query_objects
            WHERE query_object_id = :id
            """
            ),
            {"id": query_object_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ValueError(f"QueryObject not found: {query_object_id!r}")
    return dict(row)


def _load_seller_profile(session: Any, seller_id: str) -> dict[str, Any]:
    row = (
        session.execute(
            text(
                """
            SELECT seller_id, offer_what, offer_where, offer_who
            FROM seller_profiles
            WHERE seller_id = :id
            """
            ),
            {"id": seller_id},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise ValueError(f"SellerProfile not found: {seller_id!r}")
    seller = dict(row)
    if (
        not seller.get("offer_what")
        or not seller.get("offer_where")
        or not seller.get("offer_who")
    ):
        raise ValueError("SellerProfile missing required seller context fields")
    return seller


def _load_evidence_rows_by_ids(
    session: Any, evidence_ids: list[str]
) -> list[dict[str, Any]]:
    if not evidence_ids:
        return []
    rows = (
        session.execute(
            text(
                """
            SELECT evidence_id, source_type, observed_at, category, provenance_json
            FROM evidence
            WHERE evidence_id = ANY(CAST(:evidence_ids AS TEXT[]))
            """
            ),
            {"evidence_ids": evidence_ids},
        )
        .mappings()
        .all()
    )
    return [dict(r) for r in rows]


def _account_has_registry_alias(session: Any, account_id: str) -> bool:
    row = session.execute(
        text(
            """
            SELECT 1
            FROM account_aliases
            WHERE account_id = :account_id
              AND alias_type = 'registry'
            LIMIT 1
            """
        ),
        {"account_id": account_id},
    ).first()
    return row is not None


def _set_account_status(session: Any, account_id: str, status: str) -> None:
    session.execute(
        text("UPDATE accounts SET status = :status WHERE account_id = :account_id"),
        {"status": status, "account_id": account_id},
    )


def _enqueue_people_search_work_item(
    *,
    session: Any,
    account_id: str,
    parent_work_item: dict[str, Any],
    effective_input_key: str,
) -> bool:
    payload = {"v": 1, "data": {"account_id": account_id}}
    idempotency_key = f"people_search:{account_id}:{effective_input_key}:v1"
    work_item_id = make_work_item_id()

    result = session.execute(
        text(
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
                :work_item_id, 'account', :account_id, 'people_search',
                CAST(:payload AS JSONB), 1,
                :attempt_budget_remaining, :attempt_budget_policy,
                :idempotency_key,
                :trace_run_id, :trace_parent_work_item_id,
                :trace_correlation_id, :trace_policy_pack_id,
                now()
            )
            ON CONFLICT (idempotency_key) DO NOTHING
            """
        ),
        {
            "work_item_id": work_item_id,
            "account_id": account_id,
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


def _to_scoring_evidence(row: dict[str, Any]) -> ScoringEvidence:
    provenance = row.get("provenance_json")
    attrs = provenance if isinstance(provenance, dict) else {}
    return ScoringEvidence(
        evidence_id=row["evidence_id"],
        category=resolve_evidence_category(row) or "unknown",
        source_type=row.get("source_type") or "",
        observed_at=row.get("observed_at"),
        attrs=attrs,
    )


def _resolve_used_evidence(
    *,
    session: Any,
    account: dict[str, Any],
    payload_evidence_ids: list[str] | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if payload_evidence_ids is not None:
        target_ids = payload_evidence_ids
    else:
        target_ids = [
            eid
            for eid in (account.get("evidence_ids") or [])
            if isinstance(eid, str) and eid
        ]

    evidence_rows = _load_evidence_rows_by_ids(session, target_ids)
    found_ids = {row["evidence_id"] for row in evidence_rows}
    missing = sorted(set(target_ids) - found_ids)
    if payload_evidence_ids is not None and missing:
        raise ValueError(f"payload evidence_ids missing: {missing}")

    allowed_rows: list[dict[str, Any]] = []
    for row in evidence_rows:
        if resolve_evidence_category(row) in {
            "firmographic",
            "persona_fit",
            "trigger",
            "technographic",
        }:
            allowed_rows.append(row)

    used_ids = sorted(row["evidence_id"] for row in allowed_rows)
    return allowed_rows, used_ids


def _scorecard_has_column(session: Any, column_name: str) -> bool:
    row = session.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'scorecards'
              AND column_name = :column_name
            LIMIT 1
            """
        ),
        {"column_name": column_name},
    ).first()
    return row is not None


def _upsert_scorecard(session: Any, scorecard: Any) -> None:
    has_scoring_version = _scorecard_has_column(session, "scoring_version")
    has_evidence_snapshot_hash = _scorecard_has_column(
        session, "evidence_snapshot_hash"
    )

    if has_scoring_version and has_evidence_snapshot_hash:
        sql = text(
            """
            INSERT INTO scorecards (
                scorecard_id, entity_ref_type, entity_ref_id, policy_pack_id,
                fit_score, fit_confidence, fit_reasons_json,
                intent_score, intent_confidence, intent_reasons_json,
                scoring_version, evidence_snapshot_hash,
                computed_at, v
            ) VALUES (
                :scorecard_id, 'account', :account_id, :policy_pack_id,
                :fit_score, :fit_confidence, CAST(:fit_reasons_json AS JSONB),
                :intent_score, :intent_confidence, CAST(:intent_reasons_json AS JSONB),
                :scoring_version, :evidence_snapshot_hash,
                :computed_at, 1
            )
            ON CONFLICT (scorecard_id) DO UPDATE SET
                fit_score = EXCLUDED.fit_score,
                fit_confidence = EXCLUDED.fit_confidence,
                fit_reasons_json = EXCLUDED.fit_reasons_json,
                intent_score = EXCLUDED.intent_score,
                intent_confidence = EXCLUDED.intent_confidence,
                intent_reasons_json = EXCLUDED.intent_reasons_json,
                scoring_version = EXCLUDED.scoring_version,
                evidence_snapshot_hash = EXCLUDED.evidence_snapshot_hash,
                computed_at = EXCLUDED.computed_at,
                v = scorecards.v + 1
            """
        )
    else:
        sql = text(
            """
            INSERT INTO scorecards (
                scorecard_id, entity_ref_type, entity_ref_id, policy_pack_id,
                fit_score, fit_confidence, fit_reasons_json,
                intent_score, intent_confidence, intent_reasons_json,
                computed_at, v
            ) VALUES (
                :scorecard_id, 'account', :account_id, :policy_pack_id,
                :fit_score, :fit_confidence, CAST(:fit_reasons_json AS JSONB),
                :intent_score, :intent_confidence, CAST(:intent_reasons_json AS JSONB),
                :computed_at, 1
            )
            ON CONFLICT (scorecard_id) DO UPDATE SET
                fit_score = EXCLUDED.fit_score,
                fit_confidence = EXCLUDED.fit_confidence,
                fit_reasons_json = EXCLUDED.fit_reasons_json,
                intent_score = EXCLUDED.intent_score,
                intent_confidence = EXCLUDED.intent_confidence,
                intent_reasons_json = EXCLUDED.intent_reasons_json,
                computed_at = EXCLUDED.computed_at,
                v = scorecards.v + 1
            """
        )

    params = {
        "scorecard_id": scorecard.scorecard_id,
        "account_id": scorecard.account_id,
        "policy_pack_id": scorecard.policy_pack_id,
        "fit_score": scorecard.fit.score,
        "fit_confidence": scorecard.fit.confidence,
        "fit_reasons_json": json.dumps(scorecard.fit.reasons),
        "intent_score": scorecard.intent.score,
        "intent_confidence": scorecard.intent.confidence,
        "intent_reasons_json": json.dumps(scorecard.intent.reasons),
        "computed_at": scorecard.computed_at,
        "scoring_version": scorecard.scoring_version,
        "evidence_snapshot_hash": scorecard.evidence_snapshot_hash,
    }
    session.execute(sql, params)


def handle_intent_fit_scoring(work_item: Any) -> None:
    work_item_id: str = (
        work_item["work_item_id"] if isinstance(work_item, dict) else str(work_item)
    )

    db_url = os.getenv("DATABASE_URL", "")
    engine = create_engine(_sa_url(db_url))

    try:
        with Session(engine) as session:
            try:
                wi = _load_work_item(session, work_item_id)
            except ValueError as exc:
                raise RuntimeError(f"WorkItem load failed: {exc}") from exc

            entity_ref_type = wi["entity_ref_type"]
            entity_ref_id = wi["entity_ref_id"]
            stage = wi["stage"]

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

            started_evt = build_handler_started(
                module=MODULE,
                work_item_id=work_item_id,
                entity_ref_type=entity_ref_type,
                entity_ref_id=entity_ref_id,
                stage=stage,
            )
            emit(session, started_evt)
            session.commit()

            try:
                payload = validate_scoring_payload(
                    payload_json=wi.get("payload_json"),
                    payload_version=wi.get("payload_version"),
                )
                account = _load_account(session, payload.account_id)
                query_object_id = _resolve_query_object_id_from_account_provenance(
                    account
                )
                if not query_object_id:
                    raise ValueError(
                        "Unresolved seller context (query_object_id missing)"
                    )
                qo = _load_query_object(session, query_object_id)
                _load_seller_profile(session, qo["seller_id"])
                _used_evidence_rows, used_evidence_ids = _resolve_used_evidence(
                    session=session,
                    account=account,
                    payload_evidence_ids=payload.evidence_ids,
                )

                scoring_input = [_to_scoring_evidence(r) for r in _used_evidence_rows]
                scoring_result = score_fit_intent(
                    account={
                        "domain": account.get("domain"),
                        "has_domain": bool(account.get("domain")),
                        "has_registry_id": _account_has_registry_alias(
                            session, payload.account_id
                        ),
                        "conflicting_firmographics_unresolved": False,
                        "contradictory_trigger_evidence": False,
                        "conflicting_sources": False,
                        "conflicting_trigger_sources": False,
                    },
                    evidence=scoring_input,
                )
                fit = ScoreValue(
                    score=scoring_result.fit.score,
                    confidence=scoring_result.fit.confidence,
                    reasons=scoring_result.fit.reasons,
                )
                intent = ScoreValue(
                    score=scoring_result.intent.score,
                    confidence=scoring_result.intent.confidence,
                    reasons=scoring_result.intent.reasons,
                )
                scorecard = build_scorecard_upsert_input(
                    account_id=payload.account_id,
                    policy_pack_id=wi["trace_policy_pack_id"],
                    used_evidence_ids=scoring_result.used_evidence_ids,
                    fit=fit,
                    intent=intent,
                )
                _upsert_scorecard(session, scorecard)

                used_categories = {
                    ev.category
                    for ev in scoring_input
                    if ev.evidence_id in set(scoring_result.used_evidence_ids)
                }
                conflicting_firmographics_unresolved = any(
                    bool(ev.attrs.get("conflicting_firmographics"))
                    for ev in scoring_input
                    if ev.category == "firmographic"
                )
                gates = GateOutcomes(
                    hard_safety=hard_safety_gate(
                        has_domain=bool(account.get("domain")),
                        has_registry_id=_account_has_registry_alias(
                            session, payload.account_id
                        ),
                    ),
                    budget=budget_gate(
                        attempt_budget_remaining=int(wi["attempt_budget_remaining"])
                    ),
                    data_quality=data_quality_gate(
                        legal_name=account.get("name"),
                        country=account.get("country"),
                        domain=account.get("domain"),
                        conflicting_firmographics_unresolved=conflicting_firmographics_unresolved,
                    ),
                    evidence=evidence_gate(used_categories=used_categories),
                )
                lane = evaluate_lane(
                    account_status=account.get("status"),
                    fit_score=scoring_result.fit.score,
                    intent_score=scoring_result.intent.score,
                    gates=gates,
                    dedup_pass=True,
                    no_scoreable_evidence=len(_used_evidence_rows) == 0,
                    no_usable_evidence=len(scoring_result.used_evidence_ids) == 0,
                    source_conflicts_unresolved=conflicting_firmographics_unresolved,
                )

                people_search_enqueued = 0
                if lane.should_promote:
                    _set_account_status(session, payload.account_id, "target")
                if lane.should_enqueue_people_search:
                    people_search_enqueued = int(
                        _enqueue_people_search_work_item(
                            session=session,
                            account_id=payload.account_id,
                            parent_work_item=wi,
                            effective_input_key=scorecard.effective_input_key,
                        )
                    )

                if lane.parked_stage:
                    _set_work_item_stage(session, work_item_id, lane.parked_stage)

                session.commit()
            except ValueError as exc:
                _park_contract_error(
                    session=session,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    error_detail=str(exc),
                )
                return

            if lane.parked_stage:
                lane_error_code = {
                    "parked:policy_blocked": "policy_blocked",
                    "parked:budget_exhausted": "budget_exhausted",
                    "parked:no_signal": "no_signal",
                    "parked:needs_human": "needs_human",
                    "parked:no_fit": None,
                }.get(lane.parked_stage)
                terminal_evt = build_terminal_event(
                    module=MODULE,
                    work_item_id=work_item_id,
                    entity_ref_type=entity_ref_type,
                    entity_ref_id=entity_ref_id,
                    stage=lane.parked_stage,
                    event_type="work_item_parked",
                    outcome="parked",
                    error_code=lane_error_code,
                    counters={
                        "scorecards_upserted": 1,
                        "used_evidence_count": len(scoring_result.used_evidence_ids),
                    },
                    refs={
                        "account_id": payload.account_id,
                        "scorecard_id": scorecard.scorecard_id,
                        "effective_input_key": scorecard.effective_input_key,
                        "lane": lane.lane,
                    },
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
                        "scorecards_upserted": 1,
                        "used_evidence_count": len(scoring_result.used_evidence_ids),
                        "people_search_enqueued": people_search_enqueued,
                        "account_promoted": int(lane.should_promote),
                    },
                    refs={
                        "account_id": payload.account_id,
                        "scorecard_id": scorecard.scorecard_id,
                        "effective_input_key": scorecard.effective_input_key,
                        "lane": lane.lane,
                    },
                )
            emit(session, terminal_evt)
            session.commit()
    finally:
        engine.dispose()
