"""Materialize Markdown as sentence chunks."""

from __future__ import annotations

from dorje.chunking import sentence_chunks
from dorje.handles import HandleStore
from dorje.materialization import materialize_markdown_chunks
from dorje_sdk import tool


@tool(description="Materialize a Markdown/plaintext derivative as text/sentence chunk rows and optional FTS rows.", requires="derivative:text/markdown|text/plain", produces="chunks/chunks_fts")
def materialize_markdown_sentence_chunks(handle: str, max_chars: int = 1200, write_fts: bool = True) -> dict[str, object]:
    record = HandleStore().get(handle)
    return materialize_markdown_chunks(handle, materializer="materialize_markdown_sentence_chunks", chunks=sentence_chunks(record.content, max_chars=max_chars), write_fts=write_fts)
