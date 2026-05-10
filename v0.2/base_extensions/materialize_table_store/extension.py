"""Materialize table derivatives."""

from __future__ import annotations

import orjson

from dorje.db import connect, init_schema
from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Materialize a table derivative into the local table registry for future DuckDB/Parquet loading.", requires="derivative:application/vnd.dorje.table+json", produces="materialized_tables")
def materialize_table_store(handle: str, name: str = "") -> dict[str, object]:
    record = HandleStore().get(handle)
    if record.derivative_type != "table":
        raise ValueError("materialize_table_store requires a table derivative")
    payload = orjson.loads(record.content)
    table_name = name or record.label or handle
    conn = connect(".dorje/dorje.sqlite")
    init_schema(conn)
    artifact_id = f"table_{handle}"
    conn.execute(
        """
        INSERT INTO materialized_tables (id, source_handle, name, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET source_handle=excluded.source_handle, name=excluded.name, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP
        """,
        (artifact_id, handle, table_name, orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()),
    )
    conn.close()
    return {"handle": handle, "materializer": "materialize_table_store", "artifact_id": artifact_id, "name": table_name}
