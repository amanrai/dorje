"""Materialize Markdown as paragraph chunks."""

from __future__ import annotations

from dorje.chunking import paragraph_chunks
from dorje.handles import HandleStore
from dorje.materialization import materialize_markdown_chunks
from dorje_sdk import tool


@tool(description="Materialize a Markdown/plaintext derivative as text/paragraph chunk rows and optional FTS rows.", requires="derivative:text/markdown|text/plain", produces="chunks/chunks_fts")
def materialize_markdown_paragraph_chunks(handle: str, max_chars: int = 2000, write_fts: bool = True) -> dict[str, object]:
    record = HandleStore().get(handle)
    return materialize_markdown_chunks(handle, materializer="materialize_markdown_paragraph_chunks", chunks=paragraph_chunks(record.content, max_chars=max_chars), write_fts=write_fts)
