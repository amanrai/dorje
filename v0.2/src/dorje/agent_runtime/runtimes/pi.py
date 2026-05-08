"""Pi SDK-backed agent runtime placeholder."""

from dorje.agent_runtime.errors import AgentRuntimeUnavailableError
from dorje.agent_runtime.types import AgentRequest, AgentResponse


class PiAgentRuntime:
    """Agent runtime that will delegate to the Pi SDK native agent loop."""

    def __init__(self, model: str | None = None) -> None:
        self._model = model

    def run(self, request: AgentRequest) -> AgentResponse:
        raise AgentRuntimeUnavailableError(
            "PiAgentRuntime is scaffolded but not implemented yet"
        )

    def close(self) -> None:
        return
