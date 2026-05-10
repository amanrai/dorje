"""Derivative-type materializers for corpus sync."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import orjson
import yaml

from dorje.chunking import full_text_chunks, paragraph_chunks, section_chunks, sentence_chunks
from dorje.db import connect, init_schema
from dorje.handles import HandleRecord, HandleStore

ProgressCallback = Callable[[str, int, int | None], None]

DEFAULT_MATERIALIZE_CONFIG: dict[str, list[dict[str, Any]]] = {
    "extracted_markdown": [
        {
            "materializer": "text_chunks",
            "config": {"chunker": "paragraph", "max_chars": 2000, "write_fts": True},
        }
    ],
    "table": [{"materializer": "structured_artifact", "config": {}}],
    "figure": [{"materializer": "structured_artifact", "config": {}}],
    "image": [{"materializer": "structured_artifact", "config": {}}],
    "reference": [{"materializer": "structured_artifact", "config": {}}],
    "code_symbol": [{"materializer": "structured_artifact", "config": {}}],
    "style_rule": [{"materializer": "structured_artifact", "config": {}}],
}


def load_materialize_config(root: Path, max_chars: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """Load corpus-local materializer config, falling back to defaults.

    Optional file shape:

    ```yaml
    materialize:
      extracted_markdown:
        - materializer: text_chunks
          config:
            chunker: section
            max_chars: 2000
            write_fts: true
      table:
        - materializer: structured_artifact
    ```
    """
    path = root / ".dorje" / "materialize.yaml"
    if path.exists():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict) or not isinstance(loaded.get("materialize"), dict):
            raise ValueError(".dorje/materialize.yaml must contain a top-level materialize mapping")
        config = _normalize_config(loaded["materialize"])
    else:
        config = _normalize_config(DEFAULT_MATERIALIZE_CONFIG)
    if max_chars is not None:
        for entries in config.values():
            for entry in entries:
                if entry.get("materializer") == "text_chunks":
                    entry.setdefault("config", {})["max_chars"] = max_chars
    return config


def materialize_corpus(
    root: Path,
    *,
    max_chars: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    resolved_root = root.resolve()
    store = HandleStore(resolved_root / ".dorje" / "handles")
    conn = connect(resolved_root / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    config = load_materialize_config(resolved_root, max_chars=max_chars)
    rows = list(
        conn.execute(
            """
            SELECT handle, derivative_type FROM handles
            WHERE kind='derivative' AND status='active' AND derivative_type IS NOT NULL
            """
        )
    )
    active_chunk_ids: set[str] = set()
    active_artifact_ids: set[str] = set()
    counts: dict[str, int] = {"text_chunks": 0, "fts_rows": 0, "structured_artifacts": 0, "skipped": 0}
    by_materializer: dict[str, int] = {}
    for index, (handle, derivative_type) in enumerate(rows, start=1):
        if progress_callback is not None:
            progress_callback(str(handle), index - 1, len(rows))
        entries = config.get(str(derivative_type), [])
        if not entries:
            counts["skipped"] += 1
            continue
        record = store.get(str(handle))
        for entry in entries:
            materializer = str(entry.get("materializer", ""))
            materializer_config = entry.get("config", {}) if isinstance(entry.get("config", {}), dict) else {}
            if materializer == "text_chunks":
                made_chunks, made_fts = _materialize_text_chunks(conn, record, materializer_config, active_chunk_ids)
                counts["text_chunks"] += made_chunks
                counts["fts_rows"] += made_fts
                by_materializer[materializer] = by_materializer.get(materializer, 0) + made_chunks
            elif materializer == "structured_artifact":
                artifact_id = _materialize_structured_artifact(conn, record, materializer_config)
                active_artifact_ids.add(artifact_id)
                counts["structured_artifacts"] += 1
                by_materializer[materializer] = by_materializer.get(materializer, 0) + 1
            else:
                counts["skipped"] += 1
    deleted_chunks = _delete_stale_materialized_chunks(conn, active_chunk_ids)
    deleted_fts = _delete_stale_fts_rows(conn, active_chunk_ids)
    deleted_artifacts = _delete_stale_structured_artifacts(conn, active_artifact_ids)
    if progress_callback is not None:
        progress_callback("done", len(rows), len(rows))
    conn.close()
    return {
        "config": config,
        "counts": counts,
        "by_materializer": by_materializer,
        "deleted": {"chunks": deleted_chunks, "fts_rows": deleted_fts, "structured_artifacts": deleted_artifacts},
    }


def _materialize_text_chunks(conn, record: HandleRecord, config: dict[str, Any], active_chunk_ids: set[str]) -> tuple[int, int]:
    if record.content_type not in ("text/markdown", "text/plain"):
        return 0, 0
    chunker = str(config.get("chunker", "paragraph"))
    max_chars = int(config.get("max_chars", 2000))
    write_fts = bool(config.get("write_fts", True))
    chunks = _split_text(record.content, chunker=chunker, max_chars=max_chars)
    made_fts = 0
    for ordinal, chunk in enumerate(chunks):
        chunk_id = f"chunk_{record.handle}_{chunker}_{ordinal}"
        metadata = {"source_handle": record.handle, "materializer": "text_chunks", "chunker": chunker, **chunk.metadata}
        conn.execute(
            """
            INSERT INTO chunks (id, path, start_line, end_line, content, metadata_json)
            VALUES (?, ?, 0, 0, ?, ?)
            ON CONFLICT(id) DO UPDATE SET path=excluded.path, content=excluded.content, metadata_json=excluded.metadata_json
            """,
            (chunk_id, record.label, chunk.text, orjson.dumps(metadata, option=orjson.OPT_SORT_KEYS).decode()),
        )
        active_chunk_ids.add(chunk_id)
        if write_fts:
            conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
            conn.execute("INSERT INTO chunks_fts (content, path, chunk_id) VALUES (?, ?, ?)", (chunk.text, record.label, chunk_id))
            made_fts += 1
    return len(chunks), made_fts


def _materialize_structured_artifact(conn, record: HandleRecord, config: dict[str, Any]) -> str:
    del config
    artifact_id = f"artifact_{record.handle}"
    payload = {
        "source_handle": record.handle,
        "derivative_type": record.derivative_type,
        "media_type": record.content_type,
        "label": record.label,
        "content": _decode_json_or_text(record.content),
        "metadata": record.metadata,
    }
    conn.execute(
        """
        INSERT INTO materialized_artifacts (id, source_handle, derivative_type, materializer, payload_json)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET source_handle=excluded.source_handle, derivative_type=excluded.derivative_type,
            materializer=excluded.materializer, payload_json=excluded.payload_json, updated_at=CURRENT_TIMESTAMP
        """,
        (
            artifact_id,
            record.handle,
            record.derivative_type or "<none>",
            "structured_artifact",
            orjson.dumps(payload, option=orjson.OPT_SORT_KEYS).decode(),
        ),
    )
    return artifact_id


def _split_text(text: str, *, chunker: str, max_chars: int):
    if chunker == "full_text":
        return full_text_chunks(text)
    if chunker == "section":
        return section_chunks(text)
    if chunker == "paragraph":
        return paragraph_chunks(text, max_chars=max_chars)
    if chunker == "sentence":
        return sentence_chunks(text, max_chars=max_chars)
    if chunker == "strided_token":
        raise NotImplementedError("strided_token materialization requires tokenizer integration")
    raise ValueError(f"unknown text_chunks chunker: {chunker}")


def _decode_json_or_text(content: str) -> object:
    try:
        return orjson.loads(content)
    except orjson.JSONDecodeError:
        return content


def _normalize_config(raw: object) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(raw, dict):
        raise ValueError("materialize config must be a mapping")
    normalized: dict[str, list[dict[str, Any]]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        if not isinstance(value, list):
            raise ValueError(f"materialize.{key} must be a list")
        entries: list[dict[str, Any]] = []
        for entry in value:
            if not isinstance(entry, dict) or not isinstance(entry.get("materializer"), str):
                raise ValueError(f"materialize.{key} entries must contain a materializer string")
            entries.append({"materializer": entry["materializer"], "config": dict(entry.get("config", {})) if isinstance(entry.get("config", {}), dict) else {}})
        normalized[key] = entries
    return normalized


def _delete_stale_materialized_chunks(conn, active_ids: set[str]) -> int:
    existing = [row[0] for row in conn.execute("SELECT id FROM chunks WHERE id LIKE 'chunk_%'")]
    deleted = 0
    for chunk_id in existing:
        if chunk_id in active_ids:
            continue
        conn.execute("DELETE FROM chunks WHERE id=?", (chunk_id,))
        deleted += 1
    return deleted


def _delete_stale_fts_rows(conn, active_ids: set[str]) -> int:
    existing = [row[0] for row in conn.execute("SELECT chunk_id FROM chunks_fts")]
    deleted = 0
    for chunk_id in existing:
        if chunk_id in active_ids:
            continue
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
        deleted += 1
    return deleted


def _delete_stale_structured_artifacts(conn, active_ids: set[str]) -> int:
    existing = [row[0] for row in conn.execute("SELECT id FROM materialized_artifacts")]
    deleted = 0
    for artifact_id in existing:
        if artifact_id in active_ids:
            continue
        conn.execute("DELETE FROM materialized_artifacts WHERE id=?", (artifact_id,))
        deleted += 1
    return deleted
