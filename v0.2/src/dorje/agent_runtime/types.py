"""Agent runtime value types."""

from dataclasses import dataclass, field
from typing import Literal

from dorje.extensions.json_value import JsonValue

AgentRuntimeKind = Literal["pi", "native"]


@dataclass(frozen=True, slots=True)
class AgentRuntimeConfig:
    """Factory config for agent runtimes."""

    kind: AgentRuntimeKind = "pi"
    lm_provider: str | None = None
    model: str | None = None


@dataclass(frozen=True, slots=True)
class AgentRequest:
    """One agent task request."""

    query: str
    skill_names: tuple[str, ...] = ()
    max_turns: int = 8
    context: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AgentResponse:
    """Final agent task response."""

    content: str
    runtime: AgentRuntimeKind
    raw: dict[str, JsonValue] = field(default_factory=dict)
