from dataclasses import dataclass, field
from typing import Any


try:
    from agents import Agent as Agent
    AGENTS_SDK_AVAILABLE = True
except ModuleNotFoundError:
    AGENTS_SDK_AVAILABLE = False

    @dataclass
    class Agent:
        name: str
        handoff_description: str | None = None
        tools: list[Any] = field(default_factory=list)
        mcp_servers: list[Any] = field(default_factory=list)
        mcp_config: dict[str, Any] = field(default_factory=dict)
        instructions: str | None = None
        prompt: Any = None
        handoffs: list["Agent"] = field(default_factory=list)
        model: str | Any | None = None
        model_settings: Any = None
        input_guardrails: list[Any] = field(default_factory=list)
        output_guardrails: list[Any] = field(default_factory=list)
        output_type: Any = None
        hooks: Any = None
        tool_use_behavior: str = "run_llm_again"
        reset_tool_choice: bool = True

        def __class_getitem__(cls, _item: Any) -> type["Agent"]:
            return cls
