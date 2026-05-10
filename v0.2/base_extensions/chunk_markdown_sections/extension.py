"""Markdown section chunker."""

from __future__ import annotations

from dorje.chunking import chunk_markdown_handle, section_chunks
from dorje_sdk import tool


@tool(description="Chunk a Markdown/plaintext handle into heading-based text/section chunks.", requires="derivative:text/markdown|text/plain", produces="collection/full_text_chunk")
def chunk_markdown_sections(handle: str) -> dict[str, object]:
    return chunk_markdown_handle(handle, chunker_name="chunk_markdown_sections", splitter=section_chunks, label_suffix="section chunk")
