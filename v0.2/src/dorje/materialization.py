"""Shared helpers for materializer extension tools."""

from __future__ import annotations

import orjson

from dorje.chunking import TextChunk
from dorje.db import connect, init_schema
from dorje.handles import HandleStore


def materialize_markdown_chunks(
    handle: str,
    *,
    materializer: str,
    chunks: list[TextChunk],
    write_fts: bool = True,
) -> dict[str, object]:
    store = HandleStore()
    record = store.get(handle)
    if record.kind != "derivative" or record.content_type not in ("text/markdown", "text/plain"):
        raise ValueError(f"{materializer} requires a text/markdown or text/plain derivative handle")
    conn = connect(".dorje/dorje.sqlite")
    init_schema(conn)
    fts_rows = 0
    for ordinal, chunk in enumerate(chunks):
        chunk_id = f"chunk_{record.handle}_{materializer}_{ordinal}"
        metadata = {"source_handle": record.handle, "materializer": materializer, **chunk.metadata}
        conn.execute(
            """
            INSERT INTO chunks (id, path, start_line, end_line, content, metadata_json)
            VALUES (?, ?, 0, 0, ?, ?)
            ON CONFLICT(id) DO UPDATE SET path=excluded.path, content=excluded.content, metadata_json=excluded.metadata_json
            """,
            (chunk_id, record.label, chunk.text, orjson.dumps(metadata, option=orjson.OPT_SORT_KEYS).decode()),
        )
        if write_fts:
            conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
            conn.execute("INSERT INTO chunks_fts (content, path, chunk_id) VALUES (?, ?, ?)", (chunk.text, record.label, chunk_id))
            fts_rows += 1
    conn.close()
    return {"handle": handle, "materializer": materializer, "chunks": len(chunks), "fts_rows": fts_rows}
