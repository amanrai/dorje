"""File-backed typed handle store."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson

from dorje.handles.types import HandleKind, IndexState, ProvenanceRole, default_axes_for_derivative, file_ref_axes

MAX_CONTENT_CHARS = 5_000_000
MAX_FILE_TEXT_CHARS = 20_000_000


@dataclass(frozen=True, slots=True)
class HandleRecord:
    """Stored handle record.

    v0.2 originally only had stored text content. Newer records also carry
    handle axes and may represent file refs or collections. ``content`` remains
    available for backward compatibility and local text access.
    """

    handle: str
    content_type: str
    label: str
    content: str
    sha256: str
    kind: HandleKind = "derivative"
    role: ProvenanceRole = "artifact"
    index_state: IndexState = "indexable"
    path: str | None = None
    members: tuple[dict[str, Any], ...] = ()
    derivative_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HandleStore:
    """Small local handle store."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else Path.cwd() / ".dorje" / "handles"
        self._root.parent.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        content: str,
        content_type: str = "text/markdown",
        label: str = "",
        role: ProvenanceRole = "artifact",
        index_state: IndexState | None = None,
        metadata: dict[str, Any] | None = None,
        derivative_type: str | None = "manual",
    ) -> HandleRecord:
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        if len(content) > MAX_CONTENT_CHARS:
            raise ValueError("content is too large")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        axes = default_axes_for_derivative(content_type)
        resolved_index_state = index_state or axes.index_state
        resolved_metadata = metadata or {}
        handle = f"h_{_identity_hash({'kind': 'derivative', 'content_type': content_type, 'role': role, 'index_state': resolved_index_state, 'derivative_type': derivative_type, 'metadata': resolved_metadata, 'content_sha256': digest})}"
        record = HandleRecord(
            handle=handle,
            content_type=content_type,
            label=label,
            content=content,
            sha256=digest,
            kind="derivative",
            role=role,
            index_state=resolved_index_state,
            derivative_type=derivative_type,
            metadata=resolved_metadata,
        )
        self._write(record)
        return record

    def put_file_ref(
        self,
        path: Path,
        content_type: str,
        label: str = "",
        role: ProvenanceRole = "source",
        metadata: dict[str, Any] | None = None,
    ) -> HandleRecord:
        resolved = path.resolve()
        if not resolved.exists() or not resolved.is_file():
            raise FileNotFoundError(str(path))
        digest = _sha256_file(resolved)
        handle = f"hf_{digest}"
        axes = file_ref_axes(content_type, role=role)
        record = HandleRecord(
            handle=handle,
            content_type=content_type,
            label=label or resolved.name,
            content="",
            sha256=digest,
            kind="file_ref",
            role=role,
            index_state=axes.index_state,
            path=str(resolved),
            metadata=metadata or {},
        )
        self._write(record)
        return record

    def put_collection(
        self,
        members: list[dict[str, Any]],
        label: str = "",
        role: ProvenanceRole = "artifact",
        metadata: dict[str, Any] | None = None,
        derivative_type: str | None = "collection",
    ) -> HandleRecord:
        resolved_metadata = metadata or {}
        content = json.dumps(members, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        handle = f"hc_{_identity_hash({'kind': 'collection', 'role': role, 'derivative_type': derivative_type, 'metadata': resolved_metadata, 'members': members})}"
        record = HandleRecord(
            handle=handle,
            content_type="application/vnd.dorje.collection+json",
            label=label,
            content=content,
            sha256=digest,
            kind="collection",
            role=role,
            index_state="metadata",
            members=tuple(members),
            derivative_type=derivative_type,
            metadata=resolved_metadata,
        )
        self._write(record)
        return record

    def get(self, handle: str) -> HandleRecord:
        from dorje.db import connect, init_schema

        conn = connect(self._root.parent / "dorje.sqlite")
        init_schema(conn)
        row = conn.execute(
            """
            SELECT handle, kind, media_type, role, index_state, derivative_type,
                   sha256, label, file_path, metadata_json
            FROM handles WHERE handle=?
            """,
            (handle,),
        ).fetchone()
        if row is None:
            conn.close()
            raise KeyError(f"unknown handle: {handle}")
        payload_row = conn.execute("SELECT content_text FROM handle_payloads WHERE handle=?", (handle,)).fetchone()
        edge_rows = list(
            conn.execute(
                "SELECT parent_handle FROM handle_edges WHERE child_handle=? AND edge_type='contains' ORDER BY ordinal",
                (handle,),
            )
        )
        conn.close()
        handle_value, kind, media_type, role, index_state, derivative_type, sha256, label, file_path, metadata_json = row
        content = str(payload_row[0]) if payload_row is not None and payload_row[0] is not None else ""
        members: tuple[dict[str, Any], ...] = ()
        if kind == "collection":
            loaded_members = orjson.loads(content) if content else []
            if isinstance(loaded_members, list):
                members = tuple(member for member in loaded_members if isinstance(member, dict))
            elif edge_rows:
                members = tuple({"handle": str(edge[0])} for edge in edge_rows)
            if content == "":
                content = json.dumps(list(members), ensure_ascii=False, sort_keys=True)
        if kind == "file_ref" and isinstance(file_path, str) and content == "" and _is_text_media_type(str(media_type)):
            content = _read_text_file(Path(file_path))
        metadata = orjson.loads(metadata_json) if isinstance(metadata_json, str) and metadata_json else {}
        axes = default_axes_for_derivative(str(media_type)) if kind == "derivative" else None
        return HandleRecord(
            handle=str(handle_value),
            content_type=str(media_type),
            label=str(label),
            content=content,
            sha256=str(sha256),
            kind=_coerce_kind(kind),
            role=_coerce_role(role if role is not None else (axes.role if axes else "source")),
            index_state=_coerce_index_state(index_state if index_state is not None else (axes.index_state if axes else "raw")),
            path=str(file_path) if isinstance(file_path, str) else None,
            members=members,
            derivative_type=str(derivative_type) if isinstance(derivative_type, str) else None,
            metadata=dict(metadata) if isinstance(metadata, dict) else {},
        )

    def _write(self, record: HandleRecord) -> None:
        self._write_sqlite(record)

    def _write_sqlite(self, record: HandleRecord) -> None:
        from dorje.db import connect, init_schema, insert_handle_edge, upsert_handle, upsert_handle_payload

        db_path = self._root.parent / "dorje.sqlite"
        conn = connect(db_path)
        init_schema(conn)
        upsert_handle(
            conn,
            handle=record.handle,
            kind=record.kind,
            media_type=record.content_type,
            role=record.role,
            index_state=record.index_state,
            derivative_type=record.derivative_type,
            sha256=record.sha256,
            label=record.label,
            content_path=None,
            file_path=record.path,
            metadata=record.metadata,
        )
        if record.kind == "derivative":
            upsert_handle_payload(conn, handle=record.handle, content_text=record.content)
        if record.kind == "collection":
            upsert_handle_payload(conn, handle=record.handle, content_text=json.dumps(list(record.members), ensure_ascii=False, sort_keys=True))
        derived_from = record.metadata.get("derived_from")
        parents = derived_from if isinstance(derived_from, list) else [derived_from]
        for ordinal, parent in enumerate(parents):
            if isinstance(parent, str) and parent:
                insert_handle_edge(
                    conn,
                    child_handle=record.handle,
                    parent_handle=parent,
                    edge_type="derived_from",
                    ordinal=ordinal,
                )
        if record.kind == "collection":
            for ordinal, member in enumerate(record.members):
                parent = member.get("handle")
                if isinstance(parent, str) and parent:
                    insert_handle_edge(
                        conn,
                        child_handle=record.handle,
                        parent_handle=parent,
                        edge_type="contains",
                        ordinal=ordinal,
                    )
        conn.close()

    def _path(self, handle: str) -> Path:
        if not (handle.startswith("h_") or handle.startswith("hf_") or handle.startswith("hc_")):
            raise ValueError("invalid handle")
        return self._root / f"{handle}.json"


def _identity_hash(value: dict[str, Any]) -> str:
    return hashlib.sha256(orjson.dumps(value, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_text_media_type(content_type: str) -> bool:
    return content_type.startswith("text/") or content_type in {
        "application/json",
        "application/x-ndjson",
        "application/xml",
        "application/xhtml+xml",
        "application/yaml",
        "application/toml",
    }


def _read_text_file(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_TEXT_CHARS:
        raise ValueError("file_ref text file is too large to read as content")
    return path.read_text(encoding="utf-8", errors="replace")


def _coerce_kind(value: object) -> HandleKind:
    if value in ("derivative", "file_ref", "collection", "index"):
        return value  # type: ignore[return-value]
    return "derivative"


def _coerce_role(value: object) -> ProvenanceRole:
    if value in ("source", "artifact"):
        return value  # type: ignore[return-value]
    return "artifact"


def _coerce_index_state(value: object) -> IndexState:
    if value in ("raw", "indexable", "index", "metadata"):
        return value  # type: ignore[return-value]
    return "raw"
