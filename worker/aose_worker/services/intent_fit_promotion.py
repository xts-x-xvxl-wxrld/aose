"""
Epic F3 deterministic promotion and parked-lane evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateOutcomes:
    hard_safety: str  # PASS|STOP
    budget: str  # PASS|STOP
    data_quality: str  # PASS|REVIEW|STOP
    evidence: str  # PASS|REVIEW


@dataclass(frozen=True)
class LaneDecision:
    lane: str
    parked_stage: str | None
    should_promote: bool
    should_enqueue_people_search: bool


def hard_safety_gate(*, has_domain: bool, has_registry_id: bool) -> str:
    if not has_domain and not has_registry_id:
        return "STOP"
    return "PASS"


def budget_gate(*, attempt_budget_remaining: int) -> str:
    if attempt_budget_remaining <= 0:
        return "STOP"
    return "PASS"


def data_quality_gate(
    *,
    legal_name: str | None,
    country: str | None,
    domain: str | None,
    conflicting_firmographics_unresolved: bool,
) -> str:
    has_name_country = bool(legal_name) and bool(country)
    has_domain = bool(domain)
    if not has_name_country and not has_domain:
        return "STOP"
    if conflicting_firmographics_unresolved:
        return "REVIEW"
    return "PASS"


def evidence_gate(*, used_categories: set[str]) -> str:
    if len(used_categories) >= 2:
        return "PASS"
    return "REVIEW"


def evaluate_lane(
    *,
    account_status: str,
    fit_score: int,
    intent_score: int,
    gates: GateOutcomes,
    dedup_pass: bool,
    no_scoreable_evidence: bool,
    no_usable_evidence: bool,
    source_conflicts_unresolved: bool,
) -> LaneDecision:
    """
    Deterministic lane order from SPEC-F3:
      1) contract_error (handled by caller before this function)
      2) policy_blocked
      3) budget_exhausted
      4) no_signal
      5) promotion
      6) no_fit
      7) needs_human
    """
    if gates.hard_safety == "STOP":
        return LaneDecision(
            lane="policy_blocked",
            parked_stage="parked:policy_blocked",
            should_promote=False,
            should_enqueue_people_search=False,
        )

    if gates.budget == "STOP":
        return LaneDecision(
            lane="budget_exhausted",
            parked_stage="parked:budget_exhausted",
            should_promote=False,
            should_enqueue_people_search=False,
        )

    if no_scoreable_evidence or (
        fit_score == 0 and intent_score == 0 and no_usable_evidence
    ):
        return LaneDecision(
            lane="no_signal",
            parked_stage="parked:no_signal",
            should_promote=False,
            should_enqueue_people_search=False,
        )

    promote_conditions = (
        gates.hard_safety == "PASS"
        and gates.budget == "PASS"
        and gates.data_quality != "STOP"
        and gates.evidence == "PASS"
        and fit_score >= 75
        and dedup_pass
    )
    if promote_conditions:
        return LaneDecision(
            lane="promote" if account_status == "candidate" else "already_target",
            parked_stage=None,
            should_promote=account_status == "candidate",
            should_enqueue_people_search=True,
        )

    if fit_score <= 64:
        return LaneDecision(
            lane="no_fit",
            parked_stage="parked:no_fit",
            should_promote=False,
            should_enqueue_people_search=False,
        )

    review = (
        (65 <= fit_score <= 74)
        or gates.evidence == "REVIEW"
        or gates.data_quality == "REVIEW"
        or source_conflicts_unresolved
    )
    if review:
        return LaneDecision(
            lane="needs_human",
            parked_stage="parked:needs_human",
            should_promote=False,
            should_enqueue_people_search=False,
        )

    return LaneDecision(
        lane="no_fit",
        parked_stage="parked:no_fit",
        should_promote=False,
        should_enqueue_people_search=False,
    )
