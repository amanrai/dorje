"""Materialize code symbols."""

from __future__ import annotations

import orjson

from dorje.db import connect, init_schema
from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Materialize a code_symbol derivative into local symbol graph rows.", requires="derivative:text/x-code-*", produces="materialized_symbols")
def materialize_code_graph(handle: str) -> dict[str, object]:
    record = HandleStore().get(handle)
    if record.derivative_type != "code_symbol":
        raise ValueError("materialize_code_graph requires a code_symbol derivative")
    symbol_name = str(record.metadata.get("symbol_name", record.label))
    symbol_kind = str(record.metadata.get("symbol_kind", "symbol"))
    payload = {"handle": handle, "content": record.content, "metadata": record.metadata, "media_type": record.content_type}
    artifact_id = f"symbol_{handle}"
    conn = connect(".dorje/dorje.sqlite")
    init_schema(conn)
    conn.execute(
        """
        INSERT INTO materialized_symbols (id, source_handle, symbol_name, symbol_kind, payload_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET source_handle=excluded.source_handle, symbol_name=excluded.symbol_name, symbol_kind=excluded.symbol_kind, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP
        """,
        (artifact_id, handle, symbol_name, symbol_kind, orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()),
    )
    conn.close()
    return {"handle": handle, "materializer": "materialize_code_graph", "artifact_id": artifact_id, "symbol_name": symbol_name, "symbol_kind": symbol_kind}
