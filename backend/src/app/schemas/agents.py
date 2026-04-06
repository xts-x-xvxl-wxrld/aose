from pydantic import BaseModel, Field


class AgentCard(BaseModel):
    name: str
    role: str
    handoffs: list[str] = Field(default_factory=list)


class AgentSystemResponse(BaseModel):
    default_model: str | None = None
    agents: list[AgentCard]
