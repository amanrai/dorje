"""Tool decorator used by Dorje extensions."""

from collections.abc import Callable
from typing import Any, TypeAlias, TypeVar, cast

ToolFunction: TypeAlias = Callable[..., Any]
F = TypeVar("F", bound=ToolFunction)


def tool(
    func: F | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
    produces: str | None = None,
) -> F | Callable[[F], F]:
    """Mark a function as a Dorje tool.

    The decorator only attaches metadata. Dorje core performs discovery,
    JSON-boundary validation, and invocation.
    """

    def decorate(inner: F) -> F:
        setattr(inner, "__dorje_tool__", True)
        setattr(inner, "__dorje_tool_name__", name or inner.__name__)
        setattr(inner, "__dorje_tool_description__", description or (inner.__doc__ or ""))
        setattr(inner, "__dorje_tool_produces__", produces or "")
        return inner

    if func is None:
        return decorate
    return decorate(cast(F, func))
