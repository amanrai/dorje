from pathlib import Path

from dorje.db import connect, init_schema
from dorje.sync import sync_chunks, sync_fts, sync_sources


def test_sync_sources_fts_and_chunks(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha\n\nbeta", encoding="utf-8")
    (tmp_path / "b.bin").write_bytes(b"\x00\x01")

    sources = sync_sources(tmp_path)
    assert sources.added + sources.retained == 2

    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    file_refs = list(conn.execute("SELECT handle FROM handles WHERE kind='file_ref'"))
    assert len(file_refs) == 2
    conn.close()

    fts = sync_fts(tmp_path)
    assert fts.added == 1
    assert fts.skipped == 1

    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    fts_rows = list(conn.execute("SELECT chunk_id FROM chunks_fts WHERE chunk_id LIKE 'fts_%'"))
    assert len(fts_rows) == 1
    conn.close()

    chunks = sync_chunks(tmp_path, max_chars=8)
    assert chunks.added == 2
    assert chunks.skipped == 1

    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    chunk_rows = list(conn.execute("SELECT chunk_id FROM chunks_fts WHERE chunk_id LIKE 'chunk_%'"))
    assert len(chunk_rows) == 2
    conn.close()

    (tmp_path / "a.txt").unlink()
    sources_2 = sync_sources(tmp_path)
    assert sources_2.deleted == 1
    fts_2 = sync_fts(tmp_path)
    chunks_2 = sync_chunks(tmp_path)
    assert fts_2.deleted == 1
    assert chunks_2.deleted == 2
