from pathlib import Path

from dorje.db import connect, init_schema
from dorje.handles import HandleStore


def test_handle_store_writes_handles_and_edges_to_sqlite(tmp_path: Path) -> None:
    store = HandleStore(tmp_path / ".dorje" / "handles")
    source = store.put_file_ref(_write(tmp_path / "source.html", "<h1>A</h1>"), "text/html")
    derivative = store.put(
        "# A",
        content_type="text/markdown",
        metadata={"derived_from": source.handle, "converter": "test"},
        derivative_type="markdown_conversion",
    )
    collection = store.put_collection(
        [{"handle": source.handle}, {"handle": derivative.handle}],
        derivative_type="test_collection",
    )

    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    handles = {row[0] for row in conn.execute("SELECT handle FROM handles")}
    assert source.handle in handles
    assert derivative.handle in handles
    assert collection.handle in handles
    edge = conn.execute(
        "SELECT child_handle, parent_handle, edge_type FROM handle_edges WHERE child_handle=? AND parent_handle=?",
        (derivative.handle, source.handle),
    ).fetchone()
    assert edge == (derivative.handle, source.handle, "derived_from")
    member_edges = list(conn.execute("SELECT parent_handle FROM handle_edges WHERE child_handle=? AND edge_type='contains'", (collection.handle,)))
    assert {row[0] for row in member_edges} == {source.handle, derivative.handle}


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path
