"""Markdown sentence chunker."""

from __future__ import annotations

from dorje.chunking import chunk_markdown_handle, sentence_chunks
from dorje_sdk import tool


@tool(description="Chunk a Markdown/plaintext handle into sentence-bounded text/sentence chunks.", requires="derivative:text/markdown|text/plain", produces="collection/full_text_chunk")
def chunk_markdown_sentences(handle: str, max_chars: int = 1200) -> dict[str, object]:
    return chunk_markdown_handle(handle, chunker_name="chunk_markdown_sentences", splitter=lambda text: sentence_chunks(text, max_chars=max_chars), label_suffix="sentence chunk")
