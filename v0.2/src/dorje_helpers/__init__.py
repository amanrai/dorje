"""Helpers available to Python code executed by Dorje tools."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from dorje.handles import HandleStore


def iter_handles(handles: Sequence[str]) -> Iterator[str]:
    """Yield handle ids from a sequence.

    Use this inside run_python when code needs to process many handles:

        for handle in iter_handles(handles):
            ...
    """
    for handle in handles:
        if not isinstance(handle, str):
            raise TypeError("handles must contain only strings")
        yield handle


def read_handle(handle: str, max_chars: int | None = None) -> dict[str, object]:
    """Read a typed content handle.

    Use this inside run_python when code needs the content behind a handle.
    This avoids sending large handle contents through the LM context.
    """
    record = HandleStore().get(handle)
    content = record.content if max_chars is None else record.content[:max_chars]
    return {
        "handle": record.handle,
        "content_type": record.content_type,
        "label": record.label,
        "sha256": record.sha256,
        "char_count": len(record.content),
        "returned_chars": len(content),
        "truncated": len(content) < len(record.content),
        "content": content,
    }


def write_handle(content: str, content_type: str = "text/plain", label: str = "") -> dict[str, object]:
    """Write string content to a typed handle and return metadata."""
    record = HandleStore().put(content=content, content_type=content_type, label=label)
    return {
        "handle": record.handle,
        "content_type": record.content_type,
        "label": record.label,
        "sha256": record.sha256,
        "char_count": len(record.content),
    }


def store_handle(content: str, content_type: str = "text/plain", label: str = "") -> dict[str, object]:
    """Alias for write_handle."""
    return write_handle(content=content, content_type=content_type, label=label)


DORJE_HELPERS_DOCS = """
# Dorje Python Helpers

These helpers are importable inside code executed by the `run_python` tool.

Use them when your Python code needs Dorje-managed content, especially handles.
Do not call tools like `read_handle_into_context` into the LM conversation just
so Python can process the text. Pass the handle to Python and read it there.

```python
from dorje_helpers import iter_handles, read_handle, write_handle, store_handle

record = read_handle("h_...")
text = record["content"]

for handle in iter_handles(["h_...", "h_..."]):
    record = read_handle(handle)
    text = record["content"]
    # process handle content

new_record = write_handle(
    "computed output",
    content_type="text/plain",
    label="my result",
)
print(new_record["handle"])
```

## Functions

### iter_handles(handles: Sequence[str]) -> Iterator[str]

Yields handle ids from a sequence. Use this when code needs to process many
handles one by one, for example:

```python
for handle in iter_handles(handles):
    record = read_handle(handle)
    # vectorize(handle), summarize(handle), etc.
```

### read_handle(handle: str, max_chars: int | None = None) -> dict

Reads a typed content handle from Dorje's handle store.

Returns:
- handle
- content_type
- label
- sha256
- char_count
- returned_chars
- truncated
- content

### write_handle(content: str, content_type: str = "text/plain", label: str = "") -> dict

Stores string content as a typed handle.

Returns:
- handle
- content_type
- label
- sha256
- char_count

### store_handle(...)

Alias for write_handle(...).
""".strip()


def docs() -> str:
    """Return Dorje helper documentation."""
    return DORJE_HELPERS_DOCS


__all__ = ["docs", "iter_handles", "read_handle", "store_handle", "write_handle"]
