"""Content handle tools."""

from __future__ import annotations

from dorje.handles import HandleStore
from dorje_sdk import tool

DEFAULT_PREVIEW_CHARS = 1000
MAX_READ_CHARS = 200_000


@tool(description="Store text, Markdown, or JSON string content and return a typed handle.", produces="manual")
def store_handle(content: str, content_type: str = "text/markdown", label: str = "") -> dict[str, object]:
    """Store content and return handle metadata."""
    record = HandleStore().put(content=content, content_type=content_type, label=label)
    return {
        "handle": record.handle,
        "content_type": record.content_type,
        "label": record.label,
        "sha256": record.sha256,
        "char_count": len(record.content),
        "preview": record.content[:DEFAULT_PREVIEW_CHARS],
    }


@tool(description="Read content from a typed handle into LM context. Use only for bounded inspection, not data transport.")
def read_handle_into_context(handle: str, max_chars: int = MAX_READ_CHARS) -> dict[str, object]:
    """Read stored handle content into the caller/LM context for inspection."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    record = HandleStore().get(handle)
    content = record.content[:max_chars]
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
