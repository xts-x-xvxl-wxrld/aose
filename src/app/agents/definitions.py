from app.config import Settings
from app.agents.sdk import Agent


def build_account_search_agent(settings: Settings) -> Agent[None]:
    return Agent(
        name="account_search_agent",
        handoff_description="Finds and narrows target account candidates once tools are added.",
        instructions=(
            "You focus on discovering target accounts for a seller. "
            "For now you are only a skeleton agent, so do not invent tools or data sources. "
            "When implemented later, you will search for and shortlist relevant accounts."
        ),
        model=settings.openai_agent_model,
    )


def build_account_research_agent(settings: Settings) -> Agent[None]:
    return Agent(
        name="account_research_agent",
        handoff_description="Researches a selected account once external research tools are available.",
        instructions=(
            "You focus on researching a selected account. "
            "For now you are only a skeleton agent, so do not pretend to have research results. "
            "When implemented later, you will build structured account intelligence."
        ),
        model=settings.openai_agent_model,
    )


def build_contact_search_agent(settings: Settings) -> Agent[None]:
    return Agent(
        name="contact_search_agent",
        handoff_description="Finds relevant contacts inside a target account once contact tools are available.",
        instructions=(
            "You focus on identifying relevant people at a target account. "
            "For now you are only a skeleton agent, so do not fabricate contacts. "
            "When implemented later, you will use provider and research tools to propose contacts."
        ),
        model=settings.openai_agent_model,
    )


def build_orchestrator_agent(
    settings: Settings,
    *,
    handoffs: list[Agent[None]],
) -> Agent[None]:
    return Agent(
        name="orchestrator_agent",
        instructions=(
            "You are the top-level orchestrator for the outbound research system. "
            "Your job is to understand the user goal and decide whether the next specialist should be "
            "account search, account research, or contact search. "
            "Right now the system is only a skeleton, so do not claim tools, data, or completed work."
        ),
        handoffs=handoffs,
        model=settings.openai_agent_model,
    )
