"""Corpus source manifest sync.

`dorje sync` is the first corpus-local reconciliation primitive. It scans the
current folder, builds a source manifest snapshot, compares it with the previous
snapshot, and stores the new manifest under `.dorje/source_manifest.json`.
"""

from __future__ import annotations

import hashlib
import mimetypes
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Callable
from typing import Any

import orjson

from dorje.handles import HandleStore

MANIFEST_VERSION = 1
MANIFEST_PATH = Path(".dorje") / "source_manifest.json"
DEFAULT_EXCLUDE_DIRS = {".dorje", ".git", ".venv", "venv", "node_modules", "__pycache__"}


@dataclass(frozen=True, slots=True)
class SyncResult:
    root: Path
    manifest_path: Path
    added: list[str]
    modified: list[str]
    deleted: list[str]
    unchanged: list[str]
    total_sources: int

    def to_json(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "manifest_path": str(self.manifest_path),
            "total_sources": self.total_sources,
            "counts": {
                "added": len(self.added),
                "modified": len(self.modified),
                "deleted": len(self.deleted),
                "unchanged": len(self.unchanged),
            },
            "added": self.added,
            "modified": self.modified,
            "deleted": self.deleted,
            "unchanged": self.unchanged,
        }


def sync_corpus(
    root: Path | None = None,
    glob: str = "**/*",
    progress_callback: Callable[[str, int, int | None], None] | None = None,
) -> SyncResult:
    """Scan root, write a new source manifest, and return the diff."""
    resolved_root = (root or Path.cwd()).resolve()
    if not resolved_root.exists() or not resolved_root.is_dir():
        raise ValueError("root must be an existing directory")

    manifest_path = resolved_root / MANIFEST_PATH
    previous = _load_manifest(manifest_path)
    previous_sources = previous.get("sources", {}) if isinstance(previous, dict) else {}
    if not isinstance(previous_sources, dict):
        previous_sources = {}

    store = HandleStore(resolved_root / ".dorje" / "handles")
    current_sources: dict[str, dict[str, Any]] = {}
    files = _iter_files(resolved_root, glob)

    for index, file_path in enumerate(files, start=1):
        if progress_callback is not None:
            progress_callback(file_path.relative_to(resolved_root).as_posix(), index - 1, len(files))
        rel = file_path.relative_to(resolved_root).as_posix()
        stat = file_path.stat()
        digest = _sha256_file(file_path)
        media_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        previous_entry = previous_sources.get(digest)
        handle = None
        if isinstance(previous_entry, dict):
            previous_handle = previous_entry.get("handle")
            if isinstance(previous_handle, str):
                handle = previous_handle
        if handle is None:
            handle_record = store.put_file_ref(
                file_path,
                content_type=media_type,
                label=rel,
                metadata={"sha256": digest, "sync_manifest": True},
            )
            handle = handle_record.handle
        occurrence = {
            "relative_path": rel,
            "path": str(file_path),
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
        }
        if digest not in current_sources:
            current_sources[digest] = {
                "sha256": digest,
                "handle": handle,
                "kind": "file_ref",
                "role": "source",
                "media_type": media_type,
                "content_type": media_type,
                "index_state": "indexable" if _is_indexable_media_type(media_type) else "raw",
                "size_bytes": stat.st_size,
                "paths": [rel],
                "occurrences": [occurrence],
            }
        else:
            current_sources[digest]["paths"].append(rel)
            current_sources[digest]["occurrences"].append(occurrence)

    if progress_callback is not None:
        progress_callback("done", len(files), len(files))

    previous_hashes = set(previous_sources)
    current_hashes = set(current_sources)
    added = sorted(current_hashes - previous_hashes)
    deleted = sorted(previous_hashes - current_hashes)
    modified: list[str] = []
    unchanged = sorted(previous_hashes & current_hashes)
    for digest in unchanged:
        prev = previous_sources.get(digest)
        cur = current_sources[digest]
        if not isinstance(prev, dict):
            continue
        if sorted(_string_list(prev.get("paths"))) != sorted(_string_list(cur.get("paths"))):
            modified.append(digest)
    unchanged = [digest for digest in unchanged if digest not in set(modified)]

    manifest = {
        "version": MANIFEST_VERSION,
        "root": str(resolved_root),
        "created_at": datetime.now(UTC).isoformat(),
        "sources": current_sources,
        "last_diff": {
            "added": added,
            "modified": modified,
            "deleted": deleted,
            "unchanged": unchanged,
        },
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(orjson.dumps(manifest, option=orjson.OPT_INDENT_2))

    return SyncResult(
        root=resolved_root,
        manifest_path=manifest_path,
        added=added,
        modified=modified,
        deleted=deleted,
        unchanged=unchanged,
        total_sources=len(current_sources),
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = orjson.loads(path.read_bytes())
    return loaded if isinstance(loaded, dict) else {}


def _iter_files(root: Path, glob: str) -> list[Path]:
    files: list[Path] = []
    for path in root.glob(glob):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(root).parts
        if any(part in DEFAULT_EXCLUDE_DIRS for part in rel_parts):
            continue
        files.append(path)
    return sorted(files)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_indexable_media_type(media_type: str) -> bool:
    return media_type in {
        "text/markdown",
        "text/plain",
        "application/json",
        "application/x-ndjson",
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
