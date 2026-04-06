from dataclasses import dataclass

from app.agents.definitions import (
    build_account_research_agent,
    build_account_search_agent,
    build_contact_search_agent,
    build_orchestrator_agent,
)
from app.agents.sdk import Agent
from app.config import Settings
from app.schemas.agents import AgentCard, AgentSystemResponse


@dataclass(frozen=True)
class AgentSystem:
    orchestrator: Agent[None]
    account_search: Agent[None]
    account_research: Agent[None]
    contact_search: Agent[None]

    def describe(self) -> AgentSystemResponse:
        cards = [
            AgentCard(
                name=self.orchestrator.name,
                role="orchestrator",
                handoffs=[agent.name for agent in self.orchestrator.handoffs],
            ),
            AgentCard(
                name=self.account_search.name,
                role="specialist",
                handoffs=[agent.name for agent in self.account_search.handoffs],
            ),
            AgentCard(
                name=self.account_research.name,
                role="specialist",
                handoffs=[agent.name for agent in self.account_research.handoffs],
            ),
            AgentCard(
                name=self.contact_search.name,
                role="specialist",
                handoffs=[agent.name for agent in self.contact_search.handoffs],
            ),
        ]
        return AgentSystemResponse(
            default_model=self.orchestrator.model if isinstance(self.orchestrator.model, str) else None,
            agents=cards,
        )


def build_agent_system(settings: Settings) -> AgentSystem:
    account_search = build_account_search_agent(settings)
    account_research = build_account_research_agent(settings)
    contact_search = build_contact_search_agent(settings)
    orchestrator = build_orchestrator_agent(
        settings,
        handoffs=[account_search, account_research, contact_search],
    )
    return AgentSystem(
        orchestrator=orchestrator,
        account_search=account_search,
        account_research=account_research,
        contact_search=contact_search,
    )
