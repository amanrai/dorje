"""File-backed typed handle store."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import orjson

from dorje.handles.types import HandleKind, IndexState, ProvenanceRole, default_axes_for_stored_content, file_ref_axes

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
    kind: HandleKind = "stored_content"
    role: ProvenanceRole = "artifact"
    index_state: IndexState = "indexable"
    path: str | None = None
    members: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


class HandleStore:
    """Small local handle store."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else Path.cwd() / ".dorje" / "handles"
        self._root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        content: str,
        content_type: str = "text/markdown",
        label: str = "",
        role: ProvenanceRole = "artifact",
        index_state: IndexState | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> HandleRecord:
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        if len(content) > MAX_CONTENT_CHARS:
            raise ValueError("content is too large")
        handle = f"h_{uuid.uuid4().hex}"
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        axes = default_axes_for_stored_content(content_type)
        record = HandleRecord(
            handle=handle,
            content_type=content_type,
            label=label,
            content=content,
            sha256=digest,
            kind="stored_content",
            role=role,
            index_state=index_state or axes.index_state,
            metadata=metadata or {},
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
        handle = f"hf_{uuid.uuid4().hex}"
        digest = _sha256_file(resolved)
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
    ) -> HandleRecord:
        handle = f"hc_{uuid.uuid4().hex}"
        content = json.dumps(members, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
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
            metadata=metadata or {},
        )
        self._write(record)
        return record

    def get(self, handle: str) -> HandleRecord:
        path = self._path(handle)
        if not path.exists():
            raise KeyError(f"unknown handle: {handle}")
        data = orjson.loads(path.read_bytes())
        content_type = str(data.get("content_type", data.get("media_type", "text/plain")))
        kind = str(data.get("kind", "stored_content"))
        content = str(data.get("content", ""))
        file_path = data.get("path")
        if kind == "file_ref" and isinstance(file_path, str) and content == "" and _is_text_media_type(content_type):
            content = _read_text_file(Path(file_path))
        if kind == "collection" and content == "":
            content = json.dumps(data.get("members", []), ensure_ascii=False, sort_keys=True)
        axes = default_axes_for_stored_content(content_type) if kind == "stored_content" else None
        return HandleRecord(
            handle=str(data["handle"]),
            content_type=content_type,
            label=str(data.get("label", "")),
            content=content,
            sha256=str(data.get("sha256", "")),
            kind=_coerce_kind(kind),
            role=_coerce_role(data.get("role", axes.role if axes else "source")),
            index_state=_coerce_index_state(data.get("index_state", axes.index_state if axes else "raw")),
            path=str(file_path) if isinstance(file_path, str) else None,
            members=tuple(data.get("members", ())),
            metadata=dict(data.get("metadata", {})),
        )

    def _write(self, record: HandleRecord) -> None:
        self._path(record.handle).write_bytes(
            orjson.dumps(
                {
                    "handle": record.handle,
                    "kind": record.kind,
                    "content_type": record.content_type,
                    "media_type": record.content_type,
                    "role": record.role,
                    "index_state": record.index_state,
                    "label": record.label,
                    "content": record.content if record.kind == "stored_content" else "",
                    "path": record.path,
                    "members": list(record.members),
                    "metadata": record.metadata,
                    "sha256": record.sha256,
                },
                option=orjson.OPT_INDENT_2,
            )
        )

    def _path(self, handle: str) -> Path:
        if not (handle.startswith("h_") or handle.startswith("hf_") or handle.startswith("hc_")):
            raise ValueError("invalid handle")
        return self._root / f"{handle}.json"


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
    }


def _read_text_file(path: Path) -> str:
    if path.stat().st_size > MAX_FILE_TEXT_CHARS:
        raise ValueError("file_ref text file is too large to read as content")
    return path.read_text(encoding="utf-8", errors="replace")


def _coerce_kind(value: object) -> HandleKind:
    if value in ("stored_content", "file_ref", "collection", "index"):
        return value  # type: ignore[return-value]
    return "stored_content"


def _coerce_role(value: object) -> ProvenanceRole:
    if value in ("source", "artifact"):
        return value  # type: ignore[return-value]
    return "artifact"


def _coerce_index_state(value: object) -> IndexState:
    if value in ("raw", "indexable", "index", "metadata"):
        return value  # type: ignore[return-value]
    return "raw"
