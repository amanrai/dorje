"""Public LM value types."""

from dataclasses import dataclass, field
from typing import Literal

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
LMOutputMode = Literal["text", "json"]


@dataclass(frozen=True, slots=True)
class LMRequest:
    """A single language-model completion request."""

    prompt: str
    context: dict[str, JsonValue] = field(default_factory=dict)
    output: LMOutputMode = "text"
    timeout_s: float = 120.0
    model: str | None = None
    system: str | None = None
    schema: dict[str, JsonValue] | None = None


@dataclass(frozen=True, slots=True)
class LMResponse:
    """A language-model completion response."""

    text: str
    model: str | None = None
    provider: str | None = None
    raw: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LMHealth:
    """LM provider health state."""

    ok: bool
    provider: str
    message: str
    raw: dict[str, JsonValue] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LMConfig:
    """Factory config for LM providers."""

    provider: Literal["echo", "pi"] = "pi"
    model: str | None = None
    sidecar_command: tuple[str, ...] | None = None
    startup_timeout_s: float = 15.0
