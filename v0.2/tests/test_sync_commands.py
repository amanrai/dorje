from pathlib import Path

from dorje.db import connect, init_schema
from dorje.sync import sync_chunks, sync_extract, sync_fts, sync_sources


def test_sync_sources_extract_chunks_and_fts(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha\n\nbeta", encoding="utf-8")
    (tmp_path / "b.bin").write_bytes(b"\x00\x01")

    sources = sync_sources(tmp_path)
    assert sources.added + sources.retained == 2

    extracted = sync_extract(tmp_path)
    assert extracted.added == 1
    assert extracted.skipped == 1

    # FTS works only from chunk rows now. No chunks means no FTS rows.
    fts_before_chunks = sync_fts(tmp_path)
    assert fts_before_chunks.added == 0

    chunks = sync_chunks(tmp_path, max_chars=8)
    assert chunks.added == 2
    assert chunks.skipped == 0

    fts = sync_fts(tmp_path)
    assert fts.added == 2
    assert fts.deleted == 0

    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    chunk_rows = list(conn.execute("SELECT id FROM chunks WHERE id LIKE 'chunk_%'"))
    fts_rows = list(conn.execute("SELECT chunk_id FROM chunks_fts WHERE chunk_id LIKE 'chunk_%'"))
    assert len(chunk_rows) == 2
    assert len(fts_rows) == 2
    conn.close()

    # Simulate a stale FTS row: sync_fts should delete rows that no longer have matching chunk rows.
    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    conn.execute("INSERT INTO chunks_fts (content, path, chunk_id) VALUES ('stale', 'stale', 'stale_chunk')")
    conn.close()
    assert sync_fts(tmp_path).deleted == 1

    (tmp_path / "a.txt").unlink()
    sources_2 = sync_sources(tmp_path)
    assert sources_2.deleted == 1
    # The old Markdown derivative still exists for now, so chunks remain until
    # stale derivative invalidation exists.
    assert sync_chunks(tmp_path, max_chars=8).deleted == 0
    assert sync_fts(tmp_path).deleted == 0


def test_sync_extract_converts_html_to_markdown(tmp_path: Path) -> None:
    (tmp_path / "a.html").write_text("<h1>Title</h1><script>bad()</script><p>Body</p>", encoding="utf-8")
    sync_sources(tmp_path)

    result = sync_extract(tmp_path)

    assert result.added == 1
    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    row = conn.execute("SELECT handle FROM handles WHERE kind='derivative' AND media_type='text/markdown'").fetchone()
    assert row is not None
    conn.close()
