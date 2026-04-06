from __future__ import annotations

from app.workflows.reasoning import (
    build_account_research_prompt_spec,
    build_account_search_query_plan_prompt_spec,
    build_account_search_prompt_spec,
    build_contact_search_prompt_spec,
    validate_account_research_reasoning,
    validate_account_search_query_plan,
    validate_account_search_reasoning,
    validate_contact_search_reasoning,
)


def test_account_search_reasoning_accepts_phase3_and_legacy_shapes() -> None:
    phase3 = validate_account_search_reasoning(
        {
            "query_summary": "searched fintech operations software",
            "accepted_candidates": [
                {
                    "name": "Acme Fintech",
                    "domain": "acme.example",
                    "fit_summary": "Good fit",
                }
            ],
            "rejected_candidates": [],
            "missing_data_flags": [],
            "evidence_refs": [],
        }
    )
    legacy = validate_account_search_reasoning(
        {
            "candidates": [
                {
                    "name": "Legacy Co",
                    "domain": "legacy.example",
                }
            ]
        }
    )

    assert phase3 is not None
    assert phase3.accepted_candidates[0].name == "Acme Fintech"
    assert legacy is not None
    assert legacy.accepted_candidates[0].name == "Legacy Co"


def test_account_research_reasoning_coerces_legacy_summary_shape() -> None:
    reasoning = validate_account_research_reasoning(
        {
            "structured_research_summary": {
                "account_overview": "Acme is a fintech operator.",
                "fit_to_seller_proposition": "Operational complexity matches the seller.",
                "buying_relevance_signals": ["Hiring revops"],
                "risks_or_disqualifiers": ["Budget not confirmed"],
            },
            "uncertainty_notes": ["Public evidence is directional."],
            "research_brief_markdown": "# Brief",
        }
    )

    assert reasoning is not None
    assert reasoning.overview_summary == "Acme is a fintech operator."
    assert reasoning.fit_summary == "Operational complexity matches the seller."
    assert reasoning.key_findings == ["Hiring revops"]
    assert reasoning.risks == ["Budget not confirmed"]


def test_account_search_query_plan_reasoning_accepts_phase3_and_legacy_shapes() -> None:
    phase3 = validate_account_search_query_plan(
        {
            "search_strategy": "Prioritize B2B fintech operators with strong revops complexity.",
            "query_ideas": [
                "B2B fintech revenue operations software companies United States",
                "payments infrastructure companies United States series B series C",
            ],
            "fit_criteria": ["industry: fintech", "geography: United States"],
            "clarification_questions": [],
        }
    )
    legacy = validate_account_search_query_plan(
        {
            "strategy": "Legacy strategy",
            "queries": [
                "revenue operations fintech companies",
                "spend management platforms united states",
            ],
        }
    )

    assert phase3 is not None
    assert len(phase3.query_ideas) == 2
    assert legacy is not None
    assert legacy.search_strategy == "Legacy strategy"
    assert legacy.query_ideas[0] == "revenue operations fintech companies"


def test_contact_search_reasoning_accepts_phase3_and_legacy_shapes() -> None:
    phase3 = validate_contact_search_reasoning(
        {
            "accepted_contacts": [
                {
                    "full_name": "Pat Lee",
                    "email": "pat@example.com",
                    "source_provider": "findymail",
                    "acceptance_reason": "Strong revops match",
                }
            ],
            "rejected_contacts": [
                {
                    "full_name": "Jordan Smith",
                    "source_provider": "findymail",
                }
            ],
            "ranking_notes": "Ranked provider-backed contacts.",
            "missing_data_flags": [],
            "target_personas": ["Revenue operations leaders"],
            "selection_criteria": ["Director+ roles"],
        }
    )
    legacy_candidate_flags = validate_contact_search_reasoning(
        {
            "contacts": [
                {
                    "full_name": "Jordan Legacy",
                    "missing_data_flags": ["missing_email"],
                    "confidence_score": 0.42,
                }
            ],
            "ranked_contact_rationale": "Legacy candidate fields still validate.",
        }
    )
    legacy = validate_contact_search_reasoning(
        {
            "contacts": [
                {
                    "full_name": "Legacy Contact",
                }
            ],
            "ranked_contact_rationale": "Legacy ranked contacts.",
        }
    )

    assert phase3 is not None
    assert phase3.accepted_contacts[0].acceptance_reason == "Strong revops match"
    assert len(phase3.rejected_contacts) == 1
    assert legacy_candidate_flags is not None
    assert legacy_candidate_flags.accepted_contacts[0].missing_fields == ["missing_email"]
    assert legacy_candidate_flags.accepted_contacts[0].confidence_0_1 == 0.42
    assert legacy is not None
    assert legacy.accepted_contacts[0].full_name == "Legacy Contact"


def test_phase3_prompt_specs_are_workflow_scoped() -> None:
    assert "nuanced b2b prospect discovery" in build_account_search_query_plan_prompt_spec().lower()
    assert "precision over recall" in build_account_search_prompt_spec()
    assert "evidence-backed research snapshot" in build_account_research_prompt_spec()
    assert "provider-backed contact candidates" in build_contact_search_prompt_spec()
