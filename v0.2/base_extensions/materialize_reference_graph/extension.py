"""Materialize references."""

from __future__ import annotations

import orjson

from dorje.db import connect, init_schema
from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Materialize a reference derivative into local citation/reference graph rows.", requires="derivative:application/vnd.dorje.reference+json", produces="materialized_references")
def materialize_reference_graph(handle: str) -> dict[str, object]:
    record = HandleStore().get(handle)
    if record.derivative_type != "reference":
        raise ValueError("materialize_reference_graph requires a reference derivative")
    payload = orjson.loads(record.content)
    artifact_id = f"reference_{handle}"
    conn = connect(".dorje/dorje.sqlite")
    init_schema(conn)
    conn.execute(
        """
        INSERT INTO materialized_references (id, source_handle, payload_json)
        VALUES (?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET source_handle=excluded.source_handle, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP
        """,
        (artifact_id, handle, orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()),
    )
    conn.close()
    return {"handle": handle, "materializer": "materialize_reference_graph", "artifact_id": artifact_id}
