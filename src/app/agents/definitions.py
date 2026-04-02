from app.config import Settings
from app.agents.sdk import Agent


def build_account_search_agent(settings: Settings) -> Agent[None]:
    return Agent(
        name="account_search_agent",
        handoff_description="Finds and narrows target account candidates using provider-backed search evidence.",
        instructions=(
            "You focus on discovering target accounts for a seller. "
            "Use workflow-owned search evidence, stay precision-first, and only promote defensible candidates. "
            "Keep uncertainty explicit and do not invent missing company facts."
        ),
        model=settings.openai_agent_model,
    )


def build_account_research_agent(settings: Settings) -> Agent[None]:
    return Agent(
        name="account_research_agent",
        handoff_description="Researches a selected account with provider-backed evidence and structured synthesis.",
        instructions=(
            "You focus on researching a selected account. "
            "Synthesize compact, evidence-backed account intelligence, preserve uncertainty, "
            "and do not claim research findings that were not supported by gathered sources."
        ),
        model=settings.openai_agent_model,
    )


def build_contact_search_agent(settings: Settings) -> Agent[None]:
    return Agent(
        name="contact_search_agent",
        handoff_description="Finds relevant contacts inside a target account through provider-backed search and ranking.",
        instructions=(
            "You focus on identifying relevant people at a target account. "
            "Rank provider-backed candidates conservatively, preserve missing-data flags, "
            "and do not fabricate contacts or overstate confidence."
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
            "Keep routing rules deterministic, avoid inventing completed work, and rely on the durable workflow system."
        ),
        handoffs=handoffs,
        model=settings.openai_agent_model,
    )
