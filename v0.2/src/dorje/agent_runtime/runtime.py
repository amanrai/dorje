"""Agent runtime protocol."""

from typing import Protocol

from dorje.agent_runtime.types import AgentRequest, AgentResponse


class AgentRuntime(Protocol):
    """A provider-specific agent loop implementation."""

    def run(self, request: AgentRequest) -> AgentResponse:
        """Run an agent task to completion."""
        ...

    def close(self) -> None:
        """Release runtime resources."""
        ...
