from __future__ import annotations

from aose_worker.services.intent_fit_promotion import (
    GateOutcomes,
    budget_gate,
    data_quality_gate,
    evaluate_lane,
    evidence_gate,
    hard_safety_gate,
)


def test_lane_policy_blocked_precedes_others():
    lane = evaluate_lane(
        account_status="candidate",
        fit_score=95,
        intent_score=80,
        gates=GateOutcomes(
            hard_safety="STOP",
            budget="PASS",
            data_quality="PASS",
            evidence="PASS",
        ),
        dedup_pass=True,
        no_scoreable_evidence=False,
        no_usable_evidence=False,
        source_conflicts_unresolved=False,
    )
    assert lane.parked_stage == "parked:policy_blocked"


def test_lane_budget_after_policy_before_no_signal():
    lane = evaluate_lane(
        account_status="candidate",
        fit_score=95,
        intent_score=80,
        gates=GateOutcomes(
            hard_safety="PASS",
            budget="STOP",
            data_quality="PASS",
            evidence="PASS",
        ),
        dedup_pass=True,
        no_scoreable_evidence=True,
        no_usable_evidence=True,
        source_conflicts_unresolved=False,
    )
    assert lane.parked_stage == "parked:budget_exhausted"


def test_lane_no_signal_precedes_promotion():
    lane = evaluate_lane(
        account_status="candidate",
        fit_score=95,
        intent_score=85,
        gates=GateOutcomes(
            hard_safety="PASS",
            budget="PASS",
            data_quality="PASS",
            evidence="PASS",
        ),
        dedup_pass=True,
        no_scoreable_evidence=True,
        no_usable_evidence=True,
        source_conflicts_unresolved=False,
    )
    assert lane.parked_stage == "parked:no_signal"


def test_lane_promote_when_all_conditions_pass():
    lane = evaluate_lane(
        account_status="candidate",
        fit_score=80,
        intent_score=10,
        gates=GateOutcomes(
            hard_safety="PASS",
            budget="PASS",
            data_quality="PASS",
            evidence="PASS",
        ),
        dedup_pass=True,
        no_scoreable_evidence=False,
        no_usable_evidence=False,
        source_conflicts_unresolved=False,
    )
    assert lane.lane == "promote"
    assert lane.parked_stage is None
    assert lane.should_promote is True
    assert lane.should_enqueue_people_search is True


def test_lane_no_fit():
    lane = evaluate_lane(
        account_status="candidate",
        fit_score=64,
        intent_score=99,
        gates=GateOutcomes(
            hard_safety="PASS",
            budget="PASS",
            data_quality="PASS",
            evidence="PASS",
        ),
        dedup_pass=False,
        no_scoreable_evidence=False,
        no_usable_evidence=False,
        source_conflicts_unresolved=False,
    )
    assert lane.parked_stage == "parked:no_fit"


def test_lane_needs_human_for_review_band():
    lane = evaluate_lane(
        account_status="candidate",
        fit_score=70,
        intent_score=20,
        gates=GateOutcomes(
            hard_safety="PASS",
            budget="PASS",
            data_quality="PASS",
            evidence="PASS",
        ),
        dedup_pass=True,
        no_scoreable_evidence=False,
        no_usable_evidence=False,
        source_conflicts_unresolved=False,
    )
    assert lane.parked_stage == "parked:needs_human"


def test_lane_needs_human_for_gate_review():
    lane = evaluate_lane(
        account_status="candidate",
        fit_score=85,
        intent_score=20,
        gates=GateOutcomes(
            hard_safety="PASS",
            budget="PASS",
            data_quality="PASS",
            evidence="REVIEW",
        ),
        dedup_pass=True,
        no_scoreable_evidence=False,
        no_usable_evidence=False,
        source_conflicts_unresolved=False,
    )
    assert lane.parked_stage == "parked:needs_human"


def test_target_account_passes_promotion_checks_without_mutation():
    lane = evaluate_lane(
        account_status="target",
        fit_score=90,
        intent_score=20,
        gates=GateOutcomes(
            hard_safety="PASS",
            budget="PASS",
            data_quality="PASS",
            evidence="PASS",
        ),
        dedup_pass=True,
        no_scoreable_evidence=False,
        no_usable_evidence=False,
        source_conflicts_unresolved=False,
    )
    assert lane.lane == "already_target"
    assert lane.should_promote is False
    assert lane.should_enqueue_people_search is True


def test_gate_helpers():
    assert hard_safety_gate(has_domain=False, has_registry_id=False) == "STOP"
    assert hard_safety_gate(has_domain=True, has_registry_id=False) == "PASS"
    assert budget_gate(attempt_budget_remaining=0) == "STOP"
    assert budget_gate(attempt_budget_remaining=1) == "PASS"
    assert (
        data_quality_gate(
            legal_name=None,
            country="SI",
            domain=None,
            conflicting_firmographics_unresolved=False,
        )
        == "STOP"
    )
    assert (
        data_quality_gate(
            legal_name="Acme",
            country="SI",
            domain=None,
            conflicting_firmographics_unresolved=True,
        )
        == "REVIEW"
    )
    assert evidence_gate(used_categories={"firmographic", "trigger"}) == "PASS"
    assert evidence_gate(used_categories={"firmographic"}) == "REVIEW"
