from dorje.db import connect, init_schema, pack_f32


def test_sqlite_fts_and_vec_stack() -> None:
    conn = connect()
    init_schema(conn, vector_dim=4)

    conn.execute(
        "INSERT INTO chunks(id, path, content) VALUES (?, ?, ?)",
        ("c1", "example.py", "def hello(): return 'world'"),
    )
    conn.execute(
        "INSERT INTO chunks_fts(content, path, chunk_id) VALUES (?, ?, ?)",
        ("def hello(): return 'world'", "example.py", "c1"),
    )
    conn.execute(
        "INSERT INTO chunk_vectors(chunk_id, embedding) VALUES (?, ?)",
        ("c1", pack_f32([0.1, 0.2, 0.3, 0.4])),
    )

    assert conn.execute("SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH 'hello'").fetchone() == (
        "c1",
    )
    assert conn.execute(
        "SELECT chunk_id FROM chunk_vectors WHERE embedding MATCH ? AND k = 1",
        (pack_f32([0.1, 0.2, 0.3, 0.4]),),
    ).fetchone() == ("c1",)
