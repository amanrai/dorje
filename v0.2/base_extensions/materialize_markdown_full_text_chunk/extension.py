"""Materialize Markdown as one full-text chunk."""

from __future__ import annotations

from dorje.chunking import full_text_chunks
from dorje.materialization import materialize_markdown_chunks
from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Materialize a Markdown/plaintext derivative as one text/full chunk row and optional FTS row.", requires="derivative:text/markdown|text/plain", produces="chunks/chunks_fts")
def materialize_markdown_full_text_chunk(handle: str, max_chars: int = 2000, write_fts: bool = True) -> dict[str, object]:
    del max_chars
    record = HandleStore().get(handle)
    return materialize_markdown_chunks(handle, materializer="materialize_markdown_full_text_chunk", chunks=full_text_chunks(record.content), write_fts=write_fts)
