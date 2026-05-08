"""Built-in minimal tools for engine smoke tests."""

from dorje_sdk import tool


@tool(description="Echo a JSON-compatible value.")
def echo(value: object) -> object:
    """Return the provided value."""
    return value


@tool(description="Add two numbers.")
def add(a: int | float, b: int | float) -> int | float:
    """Return a + b."""
    return a + b
