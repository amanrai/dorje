"""Full-text passthrough chunker."""

from __future__ import annotations

from dorje.chunking import chunk_markdown_handle, full_text_chunks
from dorje_sdk import tool


@tool(description="Chunk a Markdown/plaintext handle by passing the full text through as one chunk.", requires="derivative:text/markdown|text/plain", produces="collection/full_text_chunk")
def chunk_full_text(handle: str) -> dict[str, object]:
    return chunk_markdown_handle(handle, chunker_name="chunk_full_text", splitter=full_text_chunks, label_suffix="full text chunk")
