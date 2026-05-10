"""Markdown paragraph chunker."""

from __future__ import annotations

from dorje.chunking import chunk_markdown_handle, paragraph_chunks
from dorje_sdk import tool


@tool(description="Chunk a Markdown/plaintext handle into paragraph-aligned text/paragraph chunks.", requires="derivative:text/markdown|text/plain", produces="collection/full_text_chunk")
def chunk_markdown_paragraphs(handle: str, max_chars: int = 2000) -> dict[str, object]:
    return chunk_markdown_handle(handle, chunker_name="chunk_markdown_paragraphs", splitter=lambda text: paragraph_chunks(text, max_chars=max_chars), label_suffix="paragraph chunk")
