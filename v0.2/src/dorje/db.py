"""SQLite/FTS/vector bootstrap for Dorje v0.2."""

from pathlib import Path
from typing import Iterable

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
    """Create the base tables for chunks, FTS, and vector search."""
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


def pack_f32(values: Iterable[float]) -> bytes:
    """Pack a Python iterable as sqlite-vec float32 bytes."""
    return sqlite_vec.serialize_float32(list(values))
