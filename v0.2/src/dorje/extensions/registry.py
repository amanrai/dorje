"""Extension tool registry."""

from collections.abc import Callable
from dataclasses import dataclass
from inspect import Parameter, signature
from typing import Any

from dorje.extensions.json_value import JsonValue, require_json_value


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Registered tool metadata."""

    name: str
    description: str
    extension_name: str
    callable: Callable[..., Any]


class ToolRegistry:
    """In-memory registry of discovered tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"duplicate tool name: {spec.name}")
        self._tools[spec.name] = spec

    def list(self) -> tuple[ToolSpec, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))

    def get(self, name: str) -> ToolSpec:
        return self._tools[name]

    def call(self, name: str, args: dict[str, JsonValue]) -> JsonValue:
        require_json_value(args, "tool args")
        spec = self.get(name)
        result = _call_with_json_args(spec.callable, args)
        return require_json_value(result, "tool result")


def _call_with_json_args(func: Callable[..., Any], args: dict[str, JsonValue]) -> object:
    sig = signature(func)
    positional: list[JsonValue] = []
    keyword: dict[str, JsonValue] = {}

    for param in sig.parameters.values():
        if param.kind in (Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD):
            raise TypeError("variadic tool parameters are not supported")
        if param.name not in args:
            if param.default is Parameter.empty:
                raise TypeError(f"missing required argument: {param.name}")
            continue
        value = args[param.name]
        if param.kind is Parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keyword[param.name] = value

    unknown = set(args) - set(sig.parameters)
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise TypeError(f"unknown tool arguments: {joined}")

    return func(*positional, **keyword)
