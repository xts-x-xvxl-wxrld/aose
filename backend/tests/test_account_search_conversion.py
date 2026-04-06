from __future__ import annotations

from app.workflows.account_search import _account_candidate_from_reasoning
from app.workflows.reasoning import validate_account_search_reasoning


def test_account_search_candidate_conversion_accepts_legacy_evidence_keys() -> None:
    reasoning = validate_account_search_reasoning(
        {
            "accepted_candidates": [
                {
                    "name": "Ramp",
                    "domain": "ramp.com",
                    "fit_summary": "Strong fintech fit.",
                    "evidence": [
                        {
                            "url": "https://www.forbes.com/lists/fintech50/",
                            "title": "Forbes Fintech 50",
                            "snippet": "The Forbes 2026 Fintech 50 list.",
                            "confidence": 82,
                            "provider": "firecrawl",
                            "metadata": {"rank": 1},
                        }
                    ],
                }
            ],
            "rejected_candidates": [],
        }
    )

    assert reasoning is not None

    candidate = _account_candidate_from_reasoning(reasoning.accepted_candidates[0])

    assert candidate.domain == "ramp.com"
    assert len(candidate.evidence) == 1
    assert candidate.evidence[0].source_type == "web"
    assert candidate.evidence[0].provider_name == "firecrawl"
    assert candidate.evidence[0].source_url == "https://www.forbes.com/lists/fintech50/"
    assert candidate.evidence[0].snippet_text == "The Forbes 2026 Fintech 50 list."
    assert candidate.evidence[0].confidence_score == 0.82
    assert candidate.evidence[0].metadata_json == {"rank": 1}
