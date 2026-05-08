"""Native provider-backed agent runtime placeholder."""

from dorje.agent_runtime.errors import AgentRuntimeUnavailableError
from dorje.agent_runtime.types import AgentRequest, AgentResponse


class NativeAgentRuntime:
    """Agent runtime that will implement a direct tool loop over an LM provider."""

    def __init__(self, lm_provider: str | None = None, model: str | None = None) -> None:
        self._lm_provider = lm_provider
        self._model = model

    def run(self, request: AgentRequest) -> AgentResponse:
        raise AgentRuntimeUnavailableError(
            "NativeAgentRuntime is scaffolded but not implemented yet"
        )

    def close(self) -> None:
        return
