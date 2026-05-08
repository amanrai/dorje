"""Agent runtime errors."""


class AgentRuntimeError(RuntimeError):
    """Base class for agent runtime errors."""


class AgentRuntimeConfigError(AgentRuntimeError):
    """Invalid agent runtime configuration."""


class AgentRuntimeUnavailableError(AgentRuntimeError):
    """Requested runtime is known but not currently implemented/available."""
