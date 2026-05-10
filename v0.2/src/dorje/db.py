"""SQLite/FTS/vector bootstrap for Dorje v0.2."""

from pathlib import Path
from typing import Iterable

import orjson

import apsw
import sqlite_vec


VECTOR_DIM = 384


def connect(path: str | Path = ":memory:") -> apsw.Connection:
    """Open a performant local SQLite connection with sqlite-vec loaded."""
    conn = apsw.Connection(str(path))
    conn.enableloadextension(True)
    conn.loadextension(sqlite_vec.loadable_path())
    conn.enableloadextension(False)

    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA mmap_size=30000000000")
    conn.execute("PRAGMA cache_size=-200000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: apsw.Connection, vector_dim: int = VECTOR_DIM) -> None:
    """Create the base tables for handles, provenance, chunks, FTS, and vectors."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS handles (
            handle TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            media_type TEXT NOT NULL,
            role TEXT NOT NULL,
            index_state TEXT NOT NULL,
            derivative_type TEXT,
            sha256 TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            content_path TEXT,
            file_path TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handles_kind ON handles(kind)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handles_media_type ON handles(media_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handles_derivative_type ON handles(derivative_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handles_sha256 ON handles(sha256)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS handle_payloads (
            handle TEXT PRIMARY KEY,
            content_text TEXT,
            content_blob BLOB,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS handle_edges (
            child_handle TEXT NOT NULL,
            parent_handle TEXT NOT NULL,
            edge_type TEXT NOT NULL,
            ordinal INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (child_handle, parent_handle, edge_type, ordinal)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handle_edges_child ON handle_edges(child_handle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handle_edges_parent ON handle_edges(parent_handle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_handle_edges_type ON handle_edges(edge_type)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS source_paths (
            sha256 TEXT NOT NULL,
            handle TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            absolute_path TEXT NOT NULL,
            media_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'active',
            PRIMARY KEY (sha256, relative_path)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_paths_handle ON source_paths(handle)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_source_paths_relative_path ON source_paths(relative_path)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_runs (
            run_id TEXT PRIMARY KEY,
            root TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT NOT NULL,
            added_count INTEGER NOT NULL,
            modified_count INTEGER NOT NULL,
            deleted_count INTEGER NOT NULL,
            unchanged_count INTEGER NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sync_run_changes (
            run_id TEXT NOT NULL,
            change_type TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            relative_path TEXT,
            details_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_run_changes_run ON sync_run_changes(run_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_run_changes_type ON sync_run_changes(change_type)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            start_line INTEGER NOT NULL DEFAULT 0,
            end_line INTEGER NOT NULL DEFAULT 0,
            content TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
            content,
            path UNINDEXED,
            chunk_id UNINDEXED,
            tokenize='unicode61 tokenchars ''_./-'''
        )
        """
    )
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS chunk_vectors USING vec0(
            chunk_id TEXT PRIMARY KEY,
            embedding float[{vector_dim}]
        )
        """
    )


def upsert_handle(
    conn: apsw.Connection,
    *,
    handle: str,
    kind: str,
    media_type: str,
    role: str,
    index_state: str,
    derivative_type: str | None,
    sha256: str,
    label: str,
    content_path: str | None,
    file_path: str | None,
    metadata: dict[str, object],
    status: str = "active",
) -> None:
    """Insert/update a handle row."""
    conn.execute(
        """
        INSERT INTO handles (
            handle, kind, media_type, role, index_state, derivative_type, sha256,
            label, content_path, file_path, metadata_json, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(handle) DO UPDATE SET
            kind=excluded.kind,
            media_type=excluded.media_type,
            role=excluded.role,
            index_state=excluded.index_state,
            derivative_type=excluded.derivative_type,
            sha256=excluded.sha256,
            label=excluded.label,
            content_path=excluded.content_path,
            file_path=excluded.file_path,
            metadata_json=excluded.metadata_json,
            status=excluded.status,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            handle,
            kind,
            media_type,
            role,
            index_state,
            derivative_type,
            sha256,
            label,
            content_path,
            file_path,
            orjson.dumps(metadata, option=orjson.OPT_SORT_KEYS).decode(),
            status,
        ),
    )


def upsert_handle_payload(
    conn: apsw.Connection,
    *,
    handle: str,
    content_text: str | None = None,
    content_blob: bytes | None = None,
) -> None:
    """Insert/update handle payload content."""
    conn.execute(
        """
        INSERT INTO handle_payloads (handle, content_text, content_blob)
        VALUES (?, ?, ?)
        ON CONFLICT(handle) DO UPDATE SET
            content_text=excluded.content_text,
            content_blob=excluded.content_blob,
            updated_at=CURRENT_TIMESTAMP
        """,
        (handle, content_text, content_blob),
    )


def insert_handle_edge(
    conn: apsw.Connection,
    *,
    child_handle: str,
    parent_handle: str,
    edge_type: str,
    ordinal: int = 0,
    metadata: dict[str, object] | None = None,
) -> None:
    """Insert a provenance/collection edge."""
    conn.execute(
        """
        INSERT OR REPLACE INTO handle_edges (
            child_handle, parent_handle, edge_type, ordinal, metadata_json
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (
            child_handle,
            parent_handle,
            edge_type,
            ordinal,
            orjson.dumps(metadata or {}, option=orjson.OPT_SORT_KEYS).decode(),
        ),
    )


def pack_f32(values: Iterable[float]) -> bytes:
    """Pack a Python iterable as sqlite-vec float32 bytes."""
    return sqlite_vec.serialize_float32(list(values))
