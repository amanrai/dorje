"""Materialize images."""

from __future__ import annotations

import orjson

from dorje.db import connect, init_schema
from dorje.handles import HandleStore
from dorje_sdk import tool


@tool(description="Materialize an image derivative into the local image registry.", requires="derivative:application/vnd.dorje.image+json", produces="materialized_images")
def materialize_image_registry(handle: str) -> dict[str, object]:
    record = HandleStore().get(handle)
    if record.derivative_type != "image":
        raise ValueError("materialize_image_registry requires an image derivative")
    payload = orjson.loads(record.content)
    media_type = str(payload.get("media_type", "application/octet-stream"))
    artifact_id = f"image_{handle}"
    conn = connect(".dorje/dorje.sqlite")
    init_schema(conn)
    conn.execute(
        """
        INSERT INTO materialized_images (id, source_handle, image_media_type, payload_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET source_handle=excluded.source_handle, image_media_type=excluded.image_media_type, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP
        """,
        (artifact_id, handle, media_type, orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode()),
    )
    conn.close()
    return {"handle": handle, "materializer": "materialize_image_registry", "artifact_id": artifact_id, "image_media_type": media_type}
