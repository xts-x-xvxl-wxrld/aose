from fastapi import APIRouter

from app.api.deps import AgentSystemDep
from app.schemas.agents import AgentSystemResponse

router = APIRouter()


@router.get("", response_model=AgentSystemResponse)
def get_agent_system_blueprint(agent_system: AgentSystemDep) -> AgentSystemResponse:
    return agent_system.describe()
