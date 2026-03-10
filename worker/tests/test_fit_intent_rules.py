from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aose_worker.services.fit_intent_rules import ScoringEvidence, score_fit_intent


NOW = datetime(2026, 3, 9, 12, 0, 0, tzinfo=timezone.utc)


def _ev(
    evidence_id: str,
    *,
    category: str,
    source_type: str = "registry_api",
    observed_at: datetime | None = None,
    **attrs,
) -> ScoringEvidence:
    return ScoringEvidence(
        evidence_id=evidence_id,
        category=category,
        source_type=source_type,
        observed_at=observed_at or NOW,
        attrs=attrs,
    )


def _account(**overrides):
    base = {
        "has_domain": True,
        "has_registry_id": True,
        "conflicting_firmographics_unresolved": False,
        "contradictory_trigger_evidence": False,
        "conflicting_sources": False,
        "conflicting_trigger_sources": False,
    }
    base.update(overrides)
    return base


def test_fit_exact_exclusive_with_adjacent():
    result = score_fit_intent(
        account=_account(),
        evidence=[
            _ev(
                "e:exact", category="firmographic", industry_or_segment_exact_match=True
            ),
            _ev(
                "e:adj",
                category="firmographic",
                industry_or_segment_adjacent_match=True,
            ),
        ],
        now=NOW,
    )
    assert result.fit.score == 35
    codes = {r["code"] for r in result.fit.reasons}
    assert "industry_or_segment_exact_match" in codes
    assert "industry_or_segment_adjacent_match" not in codes


def test_fit_all_positive_rules():
    result = score_fit_intent(
        account=_account(),
        evidence=[
            _ev(
                "e:exact", category="firmographic", industry_or_segment_exact_match=True
            ),
            _ev("e:use", category="firmographic", offer_use_case_match=True),
            _ev("e:geo", category="firmographic", geography_match=True),
            _ev("e:size", category="firmographic", size_band_match=True),
            _ev("e:tech", category="technographic", technographic_match=True),
        ],
        now=NOW,
    )
    assert result.fit.score == 100
    codes = {r["code"] for r in result.fit.reasons}
    assert {
        "industry_or_segment_exact_match",
        "offer_use_case_match",
        "geography_match",
        "size_band_match",
        "technographic_match",
    }.issubset(codes)


def test_fit_negative_rules_apply():
    result = score_fit_intent(
        account=_account(
            has_domain=False,
            has_registry_id=False,
            conflicting_firmographics_unresolved=True,
        ),
        evidence=[
            _ev(
                "e:exact", category="firmographic", industry_or_segment_exact_match=True
            ),
            _ev(
                "e:conflict",
                category="firmographic",
                conflicting_firmographics=True,
            ),
        ],
        now=NOW,
    )
    assert result.fit.score == 10  # 35 -15 -10


def test_intent_all_positive_rules():
    result = score_fit_intent(
        account=_account(),
        evidence=[
            _ev("e:h", category="trigger", signal_type="hiring_signal"),
            _ev("e:x", category="trigger", signal_type="expansion_signal"),
            _ev("e:t", category="trigger", signal_type="tender_or_procurement_signal"),
            _ev(
                "e:n",
                category="trigger",
                signal_type="new_capability_or_new_line_signal",
            ),
        ],
        now=NOW,
    )
    assert result.intent.score == 100
    assert {r["code"] for r in result.intent.reasons} == {
        "hiring_signal",
        "expansion_signal",
        "tender_or_procurement_signal",
        "new_capability_or_new_line_signal",
    }


def test_intent_negative_rules_apply():
    stale = NOW - timedelta(days=200)
    result = score_fit_intent(
        account=_account(contradictory_trigger_evidence=True),
        evidence=[
            _ev(
                "e:h",
                category="trigger",
                signal_type="hiring_signal",
                observed_at=stale,
                contradictory_trigger_evidence=True,
            ),
        ],
        now=NOW,
    )
    assert result.intent.score == 10  # 35 -15 -10
    codes = {r["code"] for r in result.intent.reasons}
    assert "stale_signal_over_180_days" in codes
    assert "contradictory_trigger_evidence" in codes


def test_confidence_penalties_fit_and_intent():
    stale = NOW - timedelta(days=200)
    result = score_fit_intent(
        account=_account(
            conflicting_sources=True,
            conflicting_trigger_sources=True,
        ),
        evidence=[
            _ev(
                "e:f1",
                category="firmographic",
                source_type="directory",
                industry_or_segment_exact_match=True,
            ),
            _ev(
                "e:f2",
                category="technographic",
                source_type="general_web_extract",
                technographic_match=True,
            ),
            _ev(
                "e:t1",
                category="trigger",
                source_type="general_web_extract",
                signal_type="hiring_signal",
                observed_at=stale,
            ),
        ],
        now=NOW,
    )
    assert result.fit.confidence == pytest.approx(0.55)  # high 0.85 - 0.20 - 0.10
    assert result.intent.confidence == pytest.approx(0.35)  # medium 0.65 - 0.20 - 0.10


def test_persona_fit_ignored_for_scoring():
    result = score_fit_intent(
        account=_account(),
        evidence=[
            _ev(
                "e:persona",
                category="persona_fit",
                industry_or_segment_exact_match=True,
                signal_type="hiring_signal",
            )
        ],
        now=NOW,
    )
    assert result.fit.score == 0
    assert result.intent.score == 0
    assert result.fit.reasons == []
    assert result.intent.reasons == []


def test_no_trigger_evidence_forces_zero_intent_and_empty_reasons():
    result = score_fit_intent(
        account=_account(),
        evidence=[_ev("e:fit", category="firmographic", geography_match=True)],
        now=NOW,
    )
    assert result.intent.score == 0
    assert result.intent.reasons == []


def test_reason_invariants_and_deterministic_output():
    evidence_a = [
        _ev("e2", category="firmographic", offer_use_case_match=True),
        _ev("e1", category="trigger", signal_type="hiring_signal"),
    ]
    evidence_b = list(reversed(evidence_a))

    r1 = score_fit_intent(account=_account(), evidence=evidence_a, now=NOW)
    r2 = score_fit_intent(account=_account(), evidence=evidence_b, now=NOW)

    assert r1.fit.score == r2.fit.score
    assert r1.intent.score == r2.intent.score
    assert r1.fit.confidence == r2.fit.confidence
    assert r1.intent.confidence == r2.intent.confidence
    assert r1.used_evidence_ids == r2.used_evidence_ids

    for reason in r1.fit.reasons + r1.intent.reasons:
        assert "code" in reason
        assert "text" in reason
        assert isinstance(reason["evidence_ids"], list)
        assert len(reason["evidence_ids"]) >= 1
