"""File-backed typed content handle store."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from pathlib import Path

import orjson

MAX_CONTENT_CHARS = 5_000_000


@dataclass(frozen=True, slots=True)
class HandleRecord:
    """Stored content handle."""

    handle: str
    content_type: str
    label: str
    content: str
    sha256: str


class HandleStore:
    """Small local content-addressable-ish handle store."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else Path.cwd() / ".dorje" / "handles"
        self._root.mkdir(parents=True, exist_ok=True)

    def put(self, content: str, content_type: str = "text/markdown", label: str = "") -> HandleRecord:
        if not isinstance(content, str):
            raise TypeError("content must be a string")
        if len(content) > MAX_CONTENT_CHARS:
            raise ValueError("content is too large")
        handle = f"h_{uuid.uuid4().hex}"
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        record = HandleRecord(
            handle=handle,
            content_type=content_type,
            label=label,
            content=content,
            sha256=digest,
        )
        self._write(record)
        return record

    def get(self, handle: str) -> HandleRecord:
        path = self._path(handle)
        if not path.exists():
            raise KeyError(f"unknown handle: {handle}")
        data = orjson.loads(path.read_bytes())
        return HandleRecord(
            handle=str(data["handle"]),
            content_type=str(data["content_type"]),
            label=str(data.get("label", "")),
            content=str(data["content"]),
            sha256=str(data["sha256"]),
        )

    def _write(self, record: HandleRecord) -> None:
        self._path(record.handle).write_bytes(
            orjson.dumps(
                {
                    "handle": record.handle,
                    "content_type": record.content_type,
                    "label": record.label,
                    "content": record.content,
                    "sha256": record.sha256,
                },
                option=orjson.OPT_INDENT_2,
            )
        )

    def _path(self, handle: str) -> Path:
        if not handle.startswith("h_"):
            raise ValueError("invalid handle")
        return self._root / f"{handle}.json"
