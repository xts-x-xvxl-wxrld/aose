from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from aose_worker.handlers.intent_fit_scoring import handle_intent_fit_scoring

NOW = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)


def _sa_url(raw: str) -> str:
    return raw.replace("postgresql://", "postgresql+psycopg://", 1)


@pytest.fixture(scope="session")
def db_engine():
    url = os.getenv("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set - skipping DB tests")
    engine = create_engine(_sa_url(url))
    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    yield engine
    engine.dispose()


def _cleanup_account_graph(session: Session, account_id: str) -> None:
    session.execute(
        text("DELETE FROM structured_events WHERE entity_ref_id = :id"),
        {"id": account_id},
    )
    session.execute(
        text("DELETE FROM work_items WHERE entity_ref_id = :id"),
        {"id": account_id},
    )
    session.execute(
        text("DELETE FROM scorecards WHERE entity_ref_id = :id"),
        {"id": account_id},
    )
    session.execute(
        text("DELETE FROM account_aliases WHERE account_id = :id"),
        {"id": account_id},
    )
    session.execute(
        text("DELETE FROM evidence WHERE evidence_id LIKE :prefix"),
        {"prefix": f"evidence:{account_id}:%"},
    )
    session.execute(
        text("DELETE FROM accounts WHERE account_id = :id"),
        {"id": account_id},
    )


def _ensure_seller_context(
    session: Session,
    *,
    seller_id: str,
    query_object_id: str,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO seller_profiles (
                seller_id, offer_what, offer_where, offer_who, offer_positioning,
                constraints_avoid_claims, constraints_allowed_channels, constraints_languages,
                policy_pack_id, created_at, v
            ) VALUES (
                :seller_id, 'Offer', '["SI"]'::jsonb, '["manufacturing"]'::jsonb, '["positioning"]'::jsonb,
                '[]'::jsonb, '["email"]'::jsonb, '["en"]'::jsonb,
                'safe_v0_1', :ts, 1
            ) ON CONFLICT (seller_id) DO NOTHING
            """
        ),
        {"seller_id": seller_id, "ts": NOW},
    )
    session.execute(
        text(
            """
            INSERT INTO query_objects (
                query_object_id, seller_id, buyer_context, priority,
                keywords, exclusions, rationale, v
            ) VALUES (
                :qid, :seller_id, 'ctx', 0.9,
                '["smt"]'::jsonb, '[]'::jsonb, 'rationale', 1
            ) ON CONFLICT (query_object_id) DO NOTHING
            """
        ),
        {"qid": query_object_id, "seller_id": seller_id},
    )


def _insert_account(
    session: Session,
    *,
    account_id: str,
    query_object_id: str,
    evidence_ids: list[str],
) -> None:
    session.execute(
        text(
            """
            INSERT INTO accounts (
                account_id, name, domain, country, provenance,
                evidence_ids, confidence, status, v
            ) VALUES (
                :account_id, 'Intent Fit Test', 'test.example.com', 'SI',
                CAST(:provenance AS JSONB), CAST(:evidence_ids AS JSONB),
                0.9, 'candidate', 1
            ) ON CONFLICT (account_id) DO UPDATE SET
                provenance = EXCLUDED.provenance,
                evidence_ids = EXCLUDED.evidence_ids
            """
        ),
        {
            "account_id": account_id,
            "provenance": json.dumps([{"query_object_id": query_object_id}]),
            "evidence_ids": json.dumps(evidence_ids),
        },
    )


def _insert_evidence(
    session: Session,
    *,
    evidence_id: str,
    category: str,
    attrs: dict[str, object],
) -> None:
    provenance = dict(attrs)
    provenance["category"] = category
    session.execute(
        text(
            """
            INSERT INTO evidence (
                evidence_id, source_type, canonical_url, captured_at, snippet,
                claim_frame, source_provider, source_ref, observed_at,
                confidence, provenance_json, content_ref_id, v
            ) VALUES (
                :evidence_id, 'web_page', 'https://example.com', :ts, 'snippet',
                'claim', 'seed', 'seed-ref', :ts,
                0.8, CAST(:provenance AS JSONB), NULL, 1
            ) ON CONFLICT (evidence_id) DO UPDATE SET
                provenance_json = EXCLUDED.provenance_json
            """
        ),
        {"evidence_id": evidence_id, "ts": NOW, "provenance": json.dumps(provenance)},
    )


def _insert_work_item(
    session: Session,
    *,
    work_item_id: str,
    account_id: str,
    payload: dict[str, object],
) -> None:
    session.execute(
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
                :work_item_id, 'account', :account_id, 'intent_fit_scoring',
                CAST(:payload_json AS JSONB), 1,
                3, 'standard',
                :idempotency_key,
                'run:intent-fit-handler', NULL,
                :trace_correlation_id, 'safe_v0_1',
                :created_at
            )
            """
        ),
        {
            "work_item_id": work_item_id,
            "account_id": account_id,
            "payload_json": json.dumps(payload),
            "idempotency_key": f"intent-fit:{work_item_id}",
            "trace_correlation_id": f"corr:{account_id}",
            "created_at": NOW,
        },
    )


def test_handler_parks_contract_error_on_payload_contract_violation(db_engine):
    account_id = "account:f1-handler-contract-error"
    work_item_id = "wi:f1-handler-contract-error"
    with Session(db_engine) as s:
        _cleanup_account_graph(s, account_id)
        s.execute(
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
                    :work_item_id, 'account', :account_id, 'intent_fit_scoring',
                    CAST(:payload_json AS JSONB), 1,
                    3, 'standard',
                    :idempotency_key,
                    'run:intent-fit-handler', NULL,
                    :trace_correlation_id, 'safe_v0_1',
                    :created_at
                )
                """
            ),
            {
                "work_item_id": work_item_id,
                "account_id": account_id,
                "payload_json": json.dumps({"v": 1, "data": {}}),
                "idempotency_key": f"intent-fit:{work_item_id}",
                "trace_correlation_id": f"corr:{account_id}",
                "created_at": NOW,
            },
        )
        s.commit()

    handle_intent_fit_scoring({"work_item_id": work_item_id})

    with Session(db_engine) as s:
        stage = s.execute(
            text("SELECT stage FROM work_items WHERE work_item_id = :id"),
            {"id": work_item_id},
        ).scalar_one()
        assert stage == "parked:contract_error"
        terminal = s.execute(
            text(
                """
                SELECT COUNT(*) FROM structured_events
                WHERE work_item_id = :id
                  AND event_type = 'work_item_failed_contract'
                  AND error_code = 'contract_error'
                """
            ),
            {"id": work_item_id},
        ).scalar_one()
        assert terminal == 1
        _cleanup_account_graph(s, account_id)
        s.execute(
            text("DELETE FROM work_items WHERE work_item_id = :id"),
            {"id": work_item_id},
        )
        s.execute(
            text("DELETE FROM structured_events WHERE work_item_id = :id"),
            {"id": work_item_id},
        )
        s.commit()


def test_handler_replay_upserts_single_scorecard_row_for_same_effective_input(
    db_engine,
):
    account_id = "account:f1-handler-replay"
    seller_id = "seller:f1-handler-replay"
    query_object_id = "qo:f1-handler-replay"
    evidence_id = f"evidence:{account_id}:1"
    wi1 = "wi:f1-handler-replay:1"
    wi2 = "wi:f1-handler-replay:2"

    with Session(db_engine) as s:
        _cleanup_account_graph(s, account_id)
        _ensure_seller_context(s, seller_id=seller_id, query_object_id=query_object_id)
        _insert_evidence(
            s,
            evidence_id=evidence_id,
            category="firmographic",
            attrs={"industry_or_segment_exact_match": True},
        )
        _insert_account(
            s,
            account_id=account_id,
            query_object_id=query_object_id,
            evidence_ids=[evidence_id],
        )
        _insert_work_item(
            s,
            work_item_id=wi1,
            account_id=account_id,
            payload={
                "v": 1,
                "data": {"account_id": account_id, "evidence_ids": [evidence_id]},
            },
        )
        _insert_work_item(
            s,
            work_item_id=wi2,
            account_id=account_id,
            payload={
                "v": 1,
                "data": {"account_id": account_id, "evidence_ids": [evidence_id]},
            },
        )
        s.commit()

    handle_intent_fit_scoring({"work_item_id": wi1})
    handle_intent_fit_scoring({"work_item_id": wi2})

    with Session(db_engine) as s:
        count_rows = s.execute(
            text("SELECT COUNT(*) FROM scorecards WHERE entity_ref_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one()
        assert count_rows == 1
        version = s.execute(
            text("SELECT v FROM scorecards WHERE entity_ref_id = :account_id"),
            {"account_id": account_id},
        ).scalar_one()
        assert version == 2
        _cleanup_account_graph(s, account_id)
        s.execute(
            text("DELETE FROM query_objects WHERE query_object_id = :id"),
            {"id": query_object_id},
        )
        s.execute(
            text("DELETE FROM seller_profiles WHERE seller_id = :id"),
            {"id": seller_id},
        )
        s.commit()


def test_handler_evidence_set_change_produces_new_snapshot_hash_and_scorecard(
    db_engine,
):
    account_id = "account:f1-handler-hash-change"
    seller_id = "seller:f1-handler-hash-change"
    query_object_id = "qo:f1-handler-hash-change"
    evidence_fit = f"evidence:{account_id}:fit"
    evidence_trigger = f"evidence:{account_id}:trigger"
    wi1 = "wi:f1-handler-hash-change:1"
    wi2 = "wi:f1-handler-hash-change:2"

    with Session(db_engine) as s:
        _cleanup_account_graph(s, account_id)
        _ensure_seller_context(s, seller_id=seller_id, query_object_id=query_object_id)
        _insert_evidence(
            s,
            evidence_id=evidence_fit,
            category="firmographic",
            attrs={"industry_or_segment_exact_match": True},
        )
        _insert_evidence(
            s,
            evidence_id=evidence_trigger,
            category="trigger",
            attrs={"signal_type": "hiring_signal"},
        )
        _insert_account(
            s,
            account_id=account_id,
            query_object_id=query_object_id,
            evidence_ids=[evidence_fit, evidence_trigger],
        )
        _insert_work_item(
            s,
            work_item_id=wi1,
            account_id=account_id,
            payload={
                "v": 1,
                "data": {"account_id": account_id, "evidence_ids": [evidence_fit]},
            },
        )
        _insert_work_item(
            s,
            work_item_id=wi2,
            account_id=account_id,
            payload={
                "v": 1,
                "data": {
                    "account_id": account_id,
                    "evidence_ids": [evidence_fit, evidence_trigger],
                },
            },
        )
        s.commit()

    handle_intent_fit_scoring({"work_item_id": wi1})
    handle_intent_fit_scoring({"work_item_id": wi2})

    with Session(db_engine) as s:
        rows = (
            s.execute(
                text(
                    """
                SELECT scorecard_id, evidence_snapshot_hash
                FROM scorecards
                WHERE entity_ref_id = :account_id
                ORDER BY computed_at ASC
                """
                ),
                {"account_id": account_id},
            )
            .mappings()
            .all()
        )
        assert len(rows) == 2
        assert rows[0]["scorecard_id"] != rows[1]["scorecard_id"]
        assert rows[0]["evidence_snapshot_hash"] != rows[1]["evidence_snapshot_hash"]
        _cleanup_account_graph(s, account_id)
        s.execute(
            text("DELETE FROM query_objects WHERE query_object_id = :id"),
            {"id": query_object_id},
        )
        s.execute(
            text("DELETE FROM seller_profiles WHERE seller_id = :id"),
            {"id": seller_id},
        )
        s.commit()
