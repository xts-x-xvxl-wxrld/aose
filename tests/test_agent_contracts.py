from app.agents.definitions import (
    build_account_research_agent,
    build_account_search_agent,
    build_contact_search_agent,
    build_orchestrator_agent,
)
from app.agents.registry import build_agent_system
from app.config import Settings


def test_agent_registry_description_stays_stable_for_smoke_inspection() -> None:
    settings = Settings()
    agent_system = build_agent_system(settings)
    description = agent_system.describe()

    assert description.default_model == settings.openai_agent_model
    assert [agent.name for agent in description.agents] == [
        "orchestrator_agent",
        "account_search_agent",
        "account_research_agent",
        "contact_search_agent",
    ]
    assert [agent.role for agent in description.agents] == [
        "orchestrator",
        "specialist",
        "specialist",
        "specialist",
    ]
    assert description.agents[0].handoffs == [
        "account_search_agent",
        "account_research_agent",
        "contact_search_agent",
    ]


def test_skeleton_agents_keep_no_fabrication_guardrails_in_instructions() -> None:
    settings = Settings()
    account_search = build_account_search_agent(settings)
    account_research = build_account_research_agent(settings)
    contact_search = build_contact_search_agent(settings)
    orchestrator = build_orchestrator_agent(
        settings,
        handoffs=[account_search, account_research, contact_search],
    )

    assert "do not invent tools or data sources" in (account_search.instructions or "")
    assert "do not pretend to have research results" in (account_research.instructions or "")
    assert "do not fabricate contacts" in (contact_search.instructions or "")
    assert "do not claim tools, data, or completed work" in (orchestrator.instructions or "")

