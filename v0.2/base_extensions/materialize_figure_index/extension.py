"""Materialize figures."""

from __future__ import annotations

import orjson

from dorje.db import connect, init_schema
from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Materialize a figure derivative into the local figure index.", requires="derivative:application/vnd.dorje.figure+json", produces="materialized_figures")
def materialize_figure_index(handle: str) -> dict[str, object]:
    record = HandleStore().get(handle)
    if record.derivative_type != "figure":
        raise ValueError("materialize_figure_index requires a figure derivative")
    payload = orjson.loads(record.content)
    caption = str(payload.get("caption", ""))
    artifact_id = f"figure_{handle}"
    conn = connect(".dorje/dorje.sqlite")
    init_schema(conn)
    conn.execute(
        """
        INSERT INTO materialized_figures (id, source_handle, caption, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET source_handle=excluded.source_handle, caption=excluded.caption, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP
        """,
        (artifact_id, handle, caption, orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()),
    )
    conn.close()
    return {"handle": handle, "materializer": "materialize_figure_index", "artifact_id": artifact_id, "caption": caption}
