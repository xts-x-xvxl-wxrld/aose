"""
Epic F2 deterministic fit/intent rule engine (v0.1).

This module is intentionally pure and side-effect free.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

FIT_POSITIVE_RULES: dict[str, int] = {
    "industry_or_segment_exact_match": 35,
    "industry_or_segment_adjacent_match": 20,
    "offer_use_case_match": 25,
    "geography_match": 15,
    "size_band_match": 10,
    "technographic_match": 15,
}
FIT_NEGATIVE_RULES: dict[str, int] = {
    "missing_website_and_registry": -15,
    "conflicting_firmographics_unresolved": -10,
}
INTENT_POSITIVE_RULES: dict[str, int] = {
    "hiring_signal": 35,
    "expansion_signal": 35,
    "tender_or_procurement_signal": 35,
    "new_capability_or_new_line_signal": 20,
}
INTENT_NEGATIVE_RULES: dict[str, int] = {
    "stale_signal_over_180_days": -15,
    "contradictory_trigger_evidence": -10,
}

SOURCE_TRUST_ORDER: tuple[str, ...] = (
    "registry_api",
    "first_party_site",
    "official_profile",
    "reputable_directory",
    "general_web_extract",
)
LOW_TRUST_TIERS: frozenset[str] = frozenset(
    {"reputable_directory", "general_web_extract"}
)

_RULE_TEXT: dict[str, str] = {
    "industry_or_segment_exact_match": "Industry/segment exact match found.",
    "industry_or_segment_adjacent_match": "Industry/segment adjacent match found.",
    "offer_use_case_match": "Offer use-case match found.",
    "geography_match": "Geography match found.",
    "size_band_match": "Size band match found.",
    "technographic_match": "Technographic match found.",
    "missing_website_and_registry": "Missing website and registry identifiers.",
    "conflicting_firmographics_unresolved": "Conflicting firmographics are unresolved.",
    "hiring_signal": "Hiring trigger signal detected.",
    "expansion_signal": "Expansion trigger signal detected.",
    "tender_or_procurement_signal": "Tender/procurement trigger signal detected.",
    "new_capability_or_new_line_signal": "New capability/new line trigger signal detected.",
    "stale_signal_over_180_days": "Trigger signal is stale over 180 days.",
    "contradictory_trigger_evidence": "Contradictory trigger evidence detected.",
}


@dataclass(frozen=True)
class ScoringEvidence:
    evidence_id: str
    category: str
    source_type: str
    observed_at: datetime | None
    attrs: dict[str, Any]


@dataclass(frozen=True)
class RuleReason:
    code: str
    text: str
    evidence_ids: list[str]


@dataclass(frozen=True)
class RuleScore:
    score: int
    confidence: float
    reasons: list[dict[str, Any]]


@dataclass(frozen=True)
class RuleScoringResult:
    fit: RuleScore
    intent: RuleScore
    used_evidence_ids: list[str]


def _clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _source_tier(ev: ScoringEvidence) -> str:
    tier = ev.attrs.get("source_trust_tier")
    if isinstance(tier, str) and tier in SOURCE_TRUST_ORDER:
        return tier
    s = ev.source_type.lower()
    if "registry" in s:
        return "registry_api"
    if "first_party" in s or "company_site" in s:
        return "first_party_site"
    if "official_profile" in s:
        return "official_profile"
    if "directory" in s:
        return "reputable_directory"
    return "general_web_extract"


def _reason(code: str, evidence_ids: list[str]) -> RuleReason:
    return RuleReason(
        code=code, text=_RULE_TEXT[code], evidence_ids=sorted(evidence_ids)
    )


def _coerce_bool(value: Any) -> bool:
    return bool(value)


def _is_stale_over_180(ev: ScoringEvidence, now: datetime) -> bool:
    if _coerce_bool(ev.attrs.get("stale_over_180_days")):
        return True
    if ev.observed_at is None:
        return False
    observed = ev.observed_at
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=timezone.utc)
    return (now - observed).days > 180


def score_fit_intent(
    *,
    account: dict[str, Any],
    evidence: list[ScoringEvidence],
    now: datetime | None = None,
) -> RuleScoringResult:
    """
    Deterministic Epic F2 scorer.

    account expected flags:
      - has_domain: bool (or domain field)
      - has_registry_id: bool
      - conflicting_firmographics_unresolved: bool
      - contradictory_trigger_evidence: bool
      - conflicting_sources: bool
      - conflicting_trigger_sources: bool
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    # Locked usage rules.
    fit_ev = [e for e in evidence if e.category in {"firmographic", "technographic"}]
    trigger_ev = [e for e in evidence if e.category == "trigger"]
    # persona_fit is explicitly ignored.
    _ = [e for e in evidence if e.category == "persona_fit"]

    fit_points = 0
    fit_reasons: list[RuleReason] = []
    intent_points = 0
    intent_reasons: list[RuleReason] = []
    used_ids: set[str] = set()

    # Fit positives.
    exact = [
        e
        for e in fit_ev
        if _coerce_bool(e.attrs.get("industry_or_segment_exact_match"))
    ]
    adjacent = [
        e
        for e in fit_ev
        if _coerce_bool(e.attrs.get("industry_or_segment_adjacent_match"))
    ]
    if exact:
        ids = [e.evidence_id for e in exact]
        fit_points += FIT_POSITIVE_RULES["industry_or_segment_exact_match"]
        fit_reasons.append(_reason("industry_or_segment_exact_match", ids))
        used_ids.update(ids)
    elif adjacent:
        ids = [e.evidence_id for e in adjacent]
        fit_points += FIT_POSITIVE_RULES["industry_or_segment_adjacent_match"]
        fit_reasons.append(_reason("industry_or_segment_adjacent_match", ids))
        used_ids.update(ids)

    use_case = [e for e in fit_ev if _coerce_bool(e.attrs.get("offer_use_case_match"))]
    if use_case:
        ids = [e.evidence_id for e in use_case]
        fit_points += FIT_POSITIVE_RULES["offer_use_case_match"]
        fit_reasons.append(_reason("offer_use_case_match", ids))
        used_ids.update(ids)

    geo = [e for e in fit_ev if _coerce_bool(e.attrs.get("geography_match"))]
    if geo:
        ids = [e.evidence_id for e in geo]
        fit_points += FIT_POSITIVE_RULES["geography_match"]
        fit_reasons.append(_reason("geography_match", ids))
        used_ids.update(ids)

    size = [e for e in fit_ev if _coerce_bool(e.attrs.get("size_band_match"))]
    if size:
        ids = [e.evidence_id for e in size]
        fit_points += FIT_POSITIVE_RULES["size_band_match"]
        fit_reasons.append(_reason("size_band_match", ids))
        used_ids.update(ids)

    techno = [
        e
        for e in fit_ev
        if e.category == "technographic"
        and _coerce_bool(e.attrs.get("technographic_match"))
    ]
    if techno:
        ids = [e.evidence_id for e in techno]
        fit_points += FIT_POSITIVE_RULES["technographic_match"]
        fit_reasons.append(_reason("technographic_match", ids))
        used_ids.update(ids)

    # Fit negatives.
    has_domain = _coerce_bool(account.get("has_domain", bool(account.get("domain"))))
    has_registry_id = _coerce_bool(account.get("has_registry_id"))
    if not has_domain and not has_registry_id:
        fit_points += FIT_NEGATIVE_RULES["missing_website_and_registry"]
        fit_reasons.append(_reason("missing_website_and_registry", []))

    if _coerce_bool(account.get("conflicting_firmographics_unresolved")):
        fit_points += FIT_NEGATIVE_RULES["conflicting_firmographics_unresolved"]
        conflict_ids = [
            e.evidence_id
            for e in fit_ev
            if _coerce_bool(e.attrs.get("conflicting_firmographics"))
        ]
        fit_reasons.append(
            _reason("conflicting_firmographics_unresolved", conflict_ids)
        )
        used_ids.update(conflict_ids)

    # Intent positives.
    signal_map = {
        "hiring_signal": "hiring_signal",
        "expansion_signal": "expansion_signal",
        "tender_or_procurement_signal": "tender_or_procurement_signal",
        "new_capability_or_new_line_signal": "new_capability_or_new_line_signal",
    }
    for rule_code, signal_type in signal_map.items():
        matches = [
            e
            for e in trigger_ev
            if str(e.attrs.get("signal_type", "")).strip().lower() == signal_type
        ]
        if matches:
            ids = [e.evidence_id for e in matches]
            intent_points += INTENT_POSITIVE_RULES[rule_code]
            intent_reasons.append(_reason(rule_code, ids))
            used_ids.update(ids)

    stale_trigger_ids = [
        e.evidence_id for e in trigger_ev if _is_stale_over_180(e, now)
    ]
    if stale_trigger_ids:
        intent_points += INTENT_NEGATIVE_RULES["stale_signal_over_180_days"]
        intent_reasons.append(_reason("stale_signal_over_180_days", stale_trigger_ids))
        used_ids.update(stale_trigger_ids)

    contradictory = _coerce_bool(account.get("contradictory_trigger_evidence")) or any(
        _coerce_bool(e.attrs.get("contradictory_trigger_evidence")) for e in trigger_ev
    )
    if contradictory:
        ids = [
            e.evidence_id
            for e in trigger_ev
            if _coerce_bool(e.attrs.get("contradictory_trigger_evidence"))
        ]
        intent_points += INTENT_NEGATIVE_RULES["contradictory_trigger_evidence"]
        intent_reasons.append(_reason("contradictory_trigger_evidence", ids))
        used_ids.update(ids)

    # Contract invariant: no trigger evidence => intent.score=0 and intent.reasons=[]
    if not trigger_ev:
        intent_points = 0
        intent_reasons = []

    fit_score = _clamp_score(fit_points)
    intent_score = _clamp_score(intent_points)

    # Confidence calculations use evidence actually consumed by scoring logic.
    fit_used = [e for e in fit_ev if e.evidence_id in used_ids]
    trigger_used = [e for e in trigger_ev if e.evidence_id in used_ids]

    fit_sources = {e.source_type for e in fit_used}
    fit_categories = {e.category for e in fit_used}
    if len(fit_sources) >= 2 and len(fit_categories) >= 2:
        fit_conf = 0.85
    elif len(fit_sources) >= 1 and len(fit_categories) >= 1:
        fit_conf = 0.65
    else:
        fit_conf = 0.40

    conflicting_sources = _coerce_bool(account.get("conflicting_sources")) or any(
        _coerce_bool(e.attrs.get("conflicting_sources")) for e in fit_used
    )
    if conflicting_sources:
        fit_conf -= 0.20
    if fit_used and all(_source_tier(e) in LOW_TRUST_TIERS for e in fit_used):
        fit_conf -= 0.10
    fit_conf = _clamp_confidence(fit_conf)

    trigger_sources = {e.source_type for e in trigger_used}
    if len(trigger_sources) >= 2:
        intent_conf = 0.85
    elif len(trigger_sources) >= 1:
        intent_conf = 0.65
    else:
        intent_conf = 0.40

    conflicting_trigger_sources = _coerce_bool(
        account.get("conflicting_trigger_sources")
    ) or any(
        _coerce_bool(e.attrs.get("conflicting_trigger_sources")) for e in trigger_used
    )
    if conflicting_trigger_sources:
        intent_conf -= 0.20
    if trigger_used and all(_is_stale_over_180(e, now) for e in trigger_used):
        intent_conf -= 0.10
    intent_conf = _clamp_confidence(intent_conf)

    # F2 reason contract: every stored reason must include one or more evidence_ids.
    fit_reason_dicts = [
        {"code": r.code, "text": r.text, "evidence_ids": r.evidence_ids}
        for r in fit_reasons
        if r.evidence_ids
    ]
    intent_reason_dicts = [
        {"code": r.code, "text": r.text, "evidence_ids": r.evidence_ids}
        for r in intent_reasons
        if r.evidence_ids
    ]

    return RuleScoringResult(
        fit=RuleScore(score=fit_score, confidence=fit_conf, reasons=fit_reason_dicts),
        intent=RuleScore(
            score=intent_score,
            confidence=intent_conf,
            reasons=intent_reason_dicts,
        ),
        used_evidence_ids=sorted(used_ids),
    )
