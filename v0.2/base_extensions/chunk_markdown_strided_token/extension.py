"""Placeholder strided token chunker."""

from __future__ import annotations

from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Placeholder for strided token-window chunking. Requires tokenizer integration before use.", requires="derivative:text/markdown|text/plain", produces="collection/full_text_chunk")
def chunk_markdown_strided_token(handle: str, window_tokens: int = 512, stride_tokens: int = 256) -> dict[str, object]:
    if window_tokens <= 0 or stride_tokens <= 0:
        raise ValueError("window_tokens and stride_tokens must be positive")
    # Validate the handle exists and is a plausible text input, but do not emit chunks yet.
    record = HandleStore().get(handle)
    if record.kind != "collection" and record.content_type not in ("text/markdown", "text/plain"):
        raise ValueError("chunk_markdown_strided_token requires text/markdown, text/plain, or a collection handle")
    raise NotImplementedError("strided token chunking requires tokenizer integration")
