"""Agent runtime factory."""

from dorje.agent_runtime.errors import AgentRuntimeConfigError
from dorje.agent_runtime.runtime import AgentRuntime
from dorje.agent_runtime.runtimes.native import NativeAgentRuntime
from dorje.agent_runtime.runtimes.pi import PiAgentRuntime
from dorje.agent_runtime.types import AgentRuntimeConfig


def create_agent_runtime(config: AgentRuntimeConfig | None = None) -> AgentRuntime:
    """Create an agent runtime from config."""
    resolved = config if config is not None else AgentRuntimeConfig()
    if resolved.kind == "pi":
        return PiAgentRuntime(model=resolved.model)
    if resolved.kind == "native":
        return NativeAgentRuntime(lm_provider=resolved.lm_provider, model=resolved.model)
    raise AgentRuntimeConfigError(f"unsupported agent runtime: {resolved.kind}")
