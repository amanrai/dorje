"""JSON boundary validation for tool IO."""

from typing import TypeAlias, cast

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


def is_json_value(value: object) -> bool:
    """Return true when value is JSON-compatible."""
    if value is None or isinstance(value, str | bool | int | float):
        return True
    if isinstance(value, list):
        return all(is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and is_json_value(item) for key, item in value.items())
    return False


def require_json_value(value: object, label: str) -> JsonValue:
    """Return value as JsonValue or raise TypeError."""
    if not is_json_value(value):
        raise TypeError(f"{label} must be JSON-compatible")
    return cast(JsonValue, value)
