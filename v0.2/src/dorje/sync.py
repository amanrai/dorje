"""Corpus source manifest sync.

`dorje sync` is the first corpus-local reconciliation primitive. It scans the
current folder, builds a source manifest snapshot, compares it with the previous
snapshot, and stores the new manifest under `.dorje/source_manifest.json`.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson
from bs4 import BeautifulSoup
from markdownify import markdownify as html_to_markdown

from dorje.content_types import guess_content_type
from dorje.db import connect, init_schema
from dorje.handles import HandleStore

MANIFEST_VERSION = 1
MANIFEST_PATH = Path(".dorje") / "source_manifest.json"
DEFAULT_EXCLUDE_DIRS = {".dorje", ".git", ".venv", "venv", "node_modules", "__pycache__"}


@dataclass(frozen=True, slots=True)
class SyncActionResult:
    action: str
    root: Path
    added: int = 0
    retained: int = 0
    deleted: int = 0
    skipped: int = 0
    details: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "root": str(self.root),
            "counts": {
                "added": self.added,
                "retained": self.retained,
                "deleted": self.deleted,
                "skipped": self.skipped,
            },
            "details": self.details,
        }


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
        media_type = guess_content_type(file_path)
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
    _write_sync_sqlite(resolved_root, current_sources, added, modified, deleted, unchanged)

    return SyncResult(
        root=resolved_root,
        manifest_path=manifest_path,
        added=added,
        modified=modified,
        deleted=deleted,
        unchanged=unchanged,
        total_sources=len(current_sources),
    )


def _write_sync_sqlite(
    root: Path,
    sources: dict[str, dict[str, Any]],
    added: list[str],
    modified: list[str],
    deleted: list[str],
    unchanged: list[str],
) -> None:
    db_path = root / ".dorje" / "dorje.sqlite"
    conn = connect(db_path)
    init_schema(conn)
    finished_at = datetime.now(UTC).isoformat()
    run_id = f"sync_{uuid.uuid4().hex}"
    conn.execute(
        """
        INSERT INTO sync_runs (
            run_id, root, started_at, finished_at, added_count, modified_count,
            deleted_count, unchanged_count, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            str(root),
            finished_at,
            finished_at,
            len(added),
            len(modified),
            len(deleted),
            len(unchanged),
            "{}",
        ),
    )
    active_hashes = set(sources)
    conn.execute("UPDATE source_paths SET status='missing' WHERE sha256 NOT IN (%s)" % ",".join("?" for _ in active_hashes), tuple(active_hashes)) if active_hashes else conn.execute("UPDATE source_paths SET status='missing'")
    for digest, source in sources.items():
        for occurrence in source.get("occurrences", []):
            if not isinstance(occurrence, dict):
                continue
            conn.execute(
                """
                INSERT INTO source_paths (
                    sha256, handle, relative_path, absolute_path, media_type,
                    size_bytes, mtime_ns, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
                ON CONFLICT(sha256, relative_path) DO UPDATE SET
                    handle=excluded.handle,
                    absolute_path=excluded.absolute_path,
                    media_type=excluded.media_type,
                    size_bytes=excluded.size_bytes,
                    mtime_ns=excluded.mtime_ns,
                    last_seen_at=CURRENT_TIMESTAMP,
                    status='active'
                """,
                (
                    digest,
                    source["handle"],
                    occurrence["relative_path"],
                    occurrence["path"],
                    source["media_type"],
                    occurrence["size_bytes"],
                    occurrence["mtime_ns"],
                ),
            )
    for change_type, hashes in (
        ("added", added),
        ("modified", modified),
        ("deleted", deleted),
        ("unchanged", unchanged),
    ):
        for digest in hashes:
            conn.execute(
                "INSERT INTO sync_run_changes (run_id, change_type, sha256, details_json) VALUES (?, ?, ?, ?)",
                (run_id, change_type, digest, "{}"),
            )
    conn.close()


def sync_summary(root: Path | None = None) -> dict[str, Any]:
    """Return counts of handles and index rows in the corpus SQLite DB."""
    resolved_root = (root or Path.cwd()).resolve()
    db_path = resolved_root / ".dorje" / "dorje.sqlite"
    if not db_path.exists():
        return {
            "root": str(resolved_root),
            "db_path": str(db_path),
            "exists": False,
            "message": "Nothing exists yet. Run dorje sync_sources first.",
            "handles_total": 0,
            "handles_by_kind": {},
            "handles_by_media_type": {},
            "handles_by_derivative_type": {},
            "handles_by_index_state": {},
            "edges_by_type": {},
            "source_paths_by_status": {},
            "chunks_total": 0,
            "fts_rows_total": 0,
        }
    conn = connect(db_path)
    init_schema(conn)
    summary: dict[str, Any] = {
        "root": str(resolved_root),
        "db_path": str(db_path),
        "exists": True,
        "handles_total": _count_scalar(conn, "SELECT count(*) FROM handles"),
        "handles_by_kind": _count_rows(conn, "SELECT kind, count(*) FROM handles GROUP BY kind ORDER BY kind"),
        "handles_by_media_type": _count_rows(conn, "SELECT media_type, count(*) FROM handles GROUP BY media_type ORDER BY media_type"),
        "handles_by_derivative_type": _count_rows(
            conn,
            "SELECT coalesce(derivative_type, '<none>'), count(*) FROM handles GROUP BY coalesce(derivative_type, '<none>') ORDER BY 1",
        ),
        "handles_by_index_state": _count_rows(conn, "SELECT index_state, count(*) FROM handles GROUP BY index_state ORDER BY index_state"),
        "edges_by_type": _count_rows(conn, "SELECT edge_type, count(*) FROM handle_edges GROUP BY edge_type ORDER BY edge_type"),
        "source_paths_by_status": _count_rows(conn, "SELECT status, count(*) FROM source_paths GROUP BY status ORDER BY status"),
        "chunks_total": _count_scalar(conn, "SELECT count(*) FROM chunks"),
        "fts_rows_total": _count_scalar(conn, "SELECT count(*) FROM chunks_fts"),
    }
    conn.close()
    return summary


def sync_sources(
    root: Path | None = None,
    glob: str = "**/*",
    progress_callback: Callable[[str, int, int | None], None] | None = None,
) -> SyncActionResult:
    """Sync file_ref source handles in SQLite against the filesystem."""
    resolved_root = (root or Path.cwd()).resolve()
    store = HandleStore(resolved_root / ".dorje" / "handles")
    conn = connect(resolved_root / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    files = _iter_files(resolved_root, glob)
    active_handles: set[str] = set()
    added = 0
    retained = 0
    for index, file_path in enumerate(files, start=1):
        if progress_callback is not None:
            progress_callback(file_path.relative_to(resolved_root).as_posix(), index - 1, len(files))
        media_type = guess_content_type(file_path)
        handle_record = store.put_file_ref(
            file_path,
            content_type=media_type,
            label=file_path.relative_to(resolved_root).as_posix(),
            metadata={"sync_sources": True},
        )
        active_handles.add(handle_record.handle)
        row = conn.execute("SELECT 1 FROM handles WHERE handle=?", (handle_record.handle,)).fetchone()
        if row is None:
            added += 1
        else:
            retained += 1
    existing = [row[0] for row in conn.execute("SELECT handle FROM handles WHERE kind='file_ref'")]
    deleted = 0
    for handle in existing:
        if handle in active_handles:
            continue
        conn.execute("DELETE FROM handle_edges WHERE child_handle=? OR parent_handle=?", (handle, handle))
        conn.execute("DELETE FROM source_paths WHERE handle=?", (handle,))
        conn.execute("DELETE FROM handles WHERE handle=?", (handle,))
        handle_path = resolved_root / ".dorje" / "handles" / f"{handle}.json"
        if handle_path.exists():
            handle_path.unlink()
        deleted += 1
    if progress_callback is not None:
        progress_callback("done", len(files), len(files))
    conn.close()
    return SyncActionResult("sync_sources", resolved_root, added=added, retained=retained, deleted=deleted)


def sync_extract(
    root: Path | None = None,
    progress_callback: Callable[[str, int, int | None], None] | None = None,
) -> SyncActionResult:
    """Extract active file_ref sources into indexable Markdown derivatives."""
    resolved_root = (root or Path.cwd()).resolve()
    store = HandleStore(resolved_root / ".dorje" / "handles")
    conn = connect(resolved_root / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    rows = list(conn.execute("SELECT handle, file_path, media_type FROM handles WHERE kind='file_ref' AND status='active'"))
    added = 0
    skipped = 0
    for index, (handle, file_path, media_type) in enumerate(rows, start=1):
        if progress_callback is not None:
            progress_callback(str(file_path), index - 1, len(rows))
        path = Path(str(file_path))
        if not path.exists():
            skipped += 1
            continue
        markdown = _extract_markdown(path, str(media_type))
        if markdown is None:
            skipped += 1
            continue
        store.put(
            markdown,
            content_type="text/markdown",
            label=f"{path.name} extracted markdown",
            index_state="indexable",
            metadata={"derived_from": str(handle), "extractor": "sync_extract", "source_media_type": str(media_type)},
            derivative_type="extracted_markdown",
        )
        added += 1
    if progress_callback is not None:
        progress_callback("done", len(rows), len(rows))
    conn.close()
    return SyncActionResult("sync_extract", resolved_root, added=added, skipped=skipped)


def sync_fts(
    root: Path | None = None,
    progress_callback: Callable[[str, int, int | None], None] | None = None,
) -> SyncActionResult:
    """Ensure chunk-level SQLite FTS is synced from chunk rows only."""
    resolved_root = (root or Path.cwd()).resolve()
    conn = connect(resolved_root / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    rows = list(conn.execute("SELECT id, path, content FROM chunks WHERE id LIKE 'chunk_%'"))
    active_ids: set[str] = set()
    added = 0
    for index, (chunk_id, path, content) in enumerate(rows, start=1):
        if progress_callback is not None:
            progress_callback(str(chunk_id), index - 1, len(rows))
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
        conn.execute("INSERT INTO chunks_fts (content, path, chunk_id) VALUES (?, ?, ?)", (content, path, chunk_id))
        active_ids.add(str(chunk_id))
        added += 1
    deleted = _delete_stale_fts_rows(conn, active_ids)
    if progress_callback is not None:
        progress_callback("done", len(rows), len(rows))
    conn.close()
    return SyncActionResult("sync_fts", resolved_root, added=added, deleted=deleted)


def sync_chunks(
    root: Path | None = None,
    max_chars: int = 2000,
    progress_callback: Callable[[str, int, int | None], None] | None = None,
) -> SyncActionResult:
    """Sync chunks from active Markdown derivative handles into SQLite FTS."""
    resolved_root = (root or Path.cwd()).resolve()
    store = HandleStore(resolved_root / ".dorje" / "handles")
    conn = connect(resolved_root / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    rows = list(conn.execute("SELECT handle FROM handles WHERE kind='derivative' AND media_type='text/markdown' AND status='active'"))
    active_ids: set[str] = set()
    added = 0
    skipped = 0
    for index, (handle,) in enumerate(rows, start=1):
        if progress_callback is not None:
            progress_callback(str(handle), index - 1, len(rows))
        record = store.get(str(handle))
        if record.content_type != "text/markdown":
            skipped += 1
            continue
        for chunk_index, chunk in enumerate(_chunk_text(record.content, max_chars=max_chars)):
            chunk_id = f"chunk_{handle}_{chunk_index}"
            conn.execute(
                """
                INSERT INTO chunks (id, path, start_line, end_line, content, metadata_json)
                VALUES (?, ?, 0, 0, ?, ?)
                ON CONFLICT(id) DO UPDATE SET path=excluded.path, content=excluded.content, metadata_json=excluded.metadata_json
                """,
                (chunk_id, record.label, chunk, orjson.dumps({"source_handle": handle, "chunk_index": chunk_index, "sync": "chunks"}).decode()),
            )
            active_ids.add(chunk_id)
            added += 1
    deleted = _delete_stale_chunks(conn, "chunk_", active_ids)
    if progress_callback is not None:
        progress_callback("done", len(rows), len(rows))
    conn.close()
    return SyncActionResult("sync_chunks", resolved_root, added=added, deleted=deleted, skipped=skipped)


def _count_scalar(conn, query: str) -> int:
    row = conn.execute(query).fetchone()
    if row is None:
        return 0
    return int(row[0])


def _count_rows(conn, query: str) -> dict[str, int]:
    return {str(key): int(count) for key, count in conn.execute(query)}


def _delete_stale_fts_rows(conn, active_ids: set[str]) -> int:
    existing = [row[0] for row in conn.execute("SELECT chunk_id FROM chunks_fts")]
    deleted = 0
    for chunk_id in existing:
        if chunk_id in active_ids:
            continue
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
        deleted += 1
    return deleted


def _delete_stale_chunks(conn, prefix: str, active_ids: set[str]) -> int:
    existing = [row[0] for row in conn.execute("SELECT id FROM chunks WHERE id LIKE ?", (f"{prefix}%",))]
    deleted = 0
    for chunk_id in existing:
        if chunk_id in active_ids:
            continue
        conn.execute("DELETE FROM chunks_fts WHERE chunk_id=?", (chunk_id,))
        conn.execute("DELETE FROM chunks WHERE id=?", (chunk_id,))
        deleted += 1
    return deleted


def _extract_markdown(path: Path, media_type: str) -> str | None:
    if media_type == "text/markdown":
        return _read_text_file(path)
    if media_type == "text/plain":
        return _read_text_file(path)
    if media_type in ("text/html", "application/xhtml+xml"):
        html = _read_text_file(path)
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "template"]):
            tag.decompose()
        return html_to_markdown(str(soup), heading_style="ATX", bullets="-").strip() + "\n"
    return None


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _chunk_text(text: str, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in text.replace("\r\n", "\n").replace("\r", "\n").split("\n\n") if part.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for paragraph in paragraphs or [text]:
        added = len(paragraph) if not current else len(paragraph) + 2
        if current and current_chars + added > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_chars = 0
        current.append(paragraph)
        current_chars += added
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _is_readable_text_media_type(media_type: str) -> bool:
    return media_type.startswith("text/") or media_type in {"application/json", "application/x-ndjson", "application/xml", "application/xhtml+xml", "application/yaml", "application/toml"}


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
    return media_type.startswith("text/") or media_type in {
        "application/json",
        "application/x-ndjson",
        "application/xml",
        "application/xhtml+xml",
        "application/yaml",
        "application/toml",
    }


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]
