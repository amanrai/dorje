"""Materialize Markdown as section chunks."""

from __future__ import annotations

from dorje.chunking import section_chunks
from dorje.handles import HandleStore
from dorje.materialization import materialize_markdown_chunks
from dorje_sdk import tool


@tool(description="Materialize a Markdown/plaintext derivative as text/section chunk rows and optional FTS rows.", requires="derivative:text/markdown|text/plain", produces="chunks/chunks_fts")
def materialize_markdown_section_chunks(handle: str, max_chars: int = 2000, write_fts: bool = True) -> dict[str, object]:
    del max_chars
    record = HandleStore().get(handle)
    return materialize_markdown_chunks(handle, materializer="materialize_markdown_section_chunks", chunks=section_chunks(record.content), write_fts=write_fts)
