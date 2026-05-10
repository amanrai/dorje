"""Materialize style rules."""

from __future__ import annotations

import orjson

from dorje.db import connect, init_schema
from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Materialize a style_rule derivative into the local style rule index.", requires="derivative:text/x-code-css|text/x-code-scss|text/x-code-sass|text/x-code-less", produces="materialized_style_rules")
def materialize_style_rule_index(handle: str) -> dict[str, object]:
    record = HandleStore().get(handle)
    if record.derivative_type != "style_rule":
        raise ValueError("materialize_style_rule_index requires a style_rule derivative")
    selector = str(record.metadata.get("selector", ""))
    payload = {"handle": handle, "content": record.content, "metadata": record.metadata, "media_type": record.content_type}
    artifact_id = f"style_rule_{handle}"
    conn = connect(".dorje/dorje.sqlite")
    init_schema(conn)
    conn.execute(
        """
        INSERT INTO materialized_style_rules (id, source_handle, selector, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET source_handle=excluded.source_handle, selector=excluded.selector, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP
        """,
        (artifact_id, handle, selector, orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()),
    )
    conn.close()
    return {"handle": handle, "materializer": "materialize_style_rule_index", "artifact_id": artifact_id, "selector": selector}
