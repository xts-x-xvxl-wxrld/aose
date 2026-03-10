from __future__ import annotations

import pytest

from aose_worker.services.intent_fit_scoring_service import (
    ScoreValue,
    build_evidence_snapshot_hash,
    build_scorecard_upsert_input,
    make_effective_scoring_input_key,
    make_scorecard_id,
    validate_reasons,
    validate_scoring_payload,
)


def test_payload_version_rejected():
    with pytest.raises(ValueError, match="Unsupported payload_version"):
        validate_scoring_payload(
            payload_json={"v": 1, "data": {"account_id": "account:SI-123"}},
            payload_version=2,
        )


def test_payload_requires_account_id():
    with pytest.raises(ValueError, match="account_id is required"):
        validate_scoring_payload(
            payload_json={"v": 1, "data": {}},
            payload_version=1,
        )


def test_evidence_snapshot_hash_is_order_independent():
    h1 = build_evidence_snapshot_hash(["evidence:b", "evidence:a"])
    h2 = build_evidence_snapshot_hash(["evidence:a", "evidence:b"])
    assert h1 == h2


def test_scorecard_id_deterministic():
    sid1 = make_scorecard_id(
        account_id="account:SI-123",
        scoring_version="fit_intent_rules_v0_1",
        evidence_snapshot_hash="abc",
        policy_pack_id="safe_v0_1",
    )
    sid2 = make_scorecard_id(
        account_id="account:SI-123",
        scoring_version="fit_intent_rules_v0_1",
        evidence_snapshot_hash="abc",
        policy_pack_id="safe_v0_1",
    )
    assert sid1 == sid2
    assert sid1.startswith("scorecard:account:SI-123:")


def test_reason_invariants_require_code_text_and_nonempty_evidence_ids():
    with pytest.raises(ValueError, match="missing non-empty code"):
        validate_reasons(
            reasons=[{"text": "x", "evidence_ids": ["evidence:1"]}],
            existing_evidence_ids={"evidence:1"},
        )
    with pytest.raises(ValueError, match="missing non-empty text"):
        validate_reasons(
            reasons=[{"code": "c", "evidence_ids": ["evidence:1"]}],
            existing_evidence_ids={"evidence:1"},
        )
    with pytest.raises(ValueError, match="non-empty evidence_ids"):
        validate_reasons(
            reasons=[{"code": "c", "text": "x", "evidence_ids": []}],
            existing_evidence_ids={"evidence:1"},
        )


def test_reason_invariants_reference_existing_evidence_ids():
    with pytest.raises(ValueError, match="unknown evidence_id"):
        validate_reasons(
            reasons=[{"code": "c", "text": "x", "evidence_ids": ["evidence:404"]}],
            existing_evidence_ids={"evidence:1"},
        )


def test_replay_safety_keys_are_stable_for_same_effective_input():
    fit = ScoreValue(score=0, confidence=0.4, reasons=[])
    intent = ScoreValue(score=0, confidence=0.4, reasons=[])
    s1 = build_scorecard_upsert_input(
        account_id="account:SI-123",
        policy_pack_id="safe_v0_1",
        used_evidence_ids=["evidence:b", "evidence:a"],
        fit=fit,
        intent=intent,
    )
    s2 = build_scorecard_upsert_input(
        account_id="account:SI-123",
        policy_pack_id="safe_v0_1",
        used_evidence_ids=["evidence:a", "evidence:b"],
        fit=fit,
        intent=intent,
    )

    assert s1.scorecard_id == s2.scorecard_id
    assert s1.effective_input_key == s2.effective_input_key
    # Explicit formula helper remains deterministic too.
    assert s1.effective_input_key == make_effective_scoring_input_key(
        account_id="account:SI-123",
        scoring_version=s1.scoring_version,
        evidence_snapshot_hash=s1.evidence_snapshot_hash,
        policy_pack_id="safe_v0_1",
    )
