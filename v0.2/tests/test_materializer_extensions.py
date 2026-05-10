from pathlib import Path
from typing import Any, cast

import orjson

from dorje.db import connect, init_schema
from dorje.extensions import load_extensions
from dorje.handles import HandleStore
from dorje.sync import sync_materialize


def _registry():
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    return load_extensions(roots=(root,))


def test_materialize_markdown_paragraph_chunks_tool(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    source = HandleStore().put("alpha\n\nbeta", content_type="text/markdown", derivative_type="extracted_markdown", label="doc")

    result = cast(dict[str, Any], _registry().call("materialize_markdown_paragraph_chunks", {"handle": source.handle, "max_chars": 8}))

    assert result["chunks"] == 2
    assert result["fts_rows"] == 2
    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (2,)
    assert conn.execute("SELECT count(*) FROM chunks_fts").fetchone() == (2,)
    conn.close()


def test_materializer_tools_write_distinct_artifact_tables(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = HandleStore()
    table = store.put(orjson.dumps({"schema": "dorje.table.v1", "columns": [], "rows": []}).decode(), content_type="application/vnd.dorje.table+json", derivative_type="table")
    symbol = store.put("def f(): pass\n", content_type="text/x-code-python", derivative_type="code_symbol", metadata={"symbol_name": "f", "symbol_kind": "function"})
    reference = store.put(orjson.dumps({"text": "ref"}).decode(), content_type="application/vnd.dorje.reference+json", derivative_type="reference")
    registry = _registry()

    registry.call("materialize_table_store", {"handle": table.handle})
    registry.call("materialize_code_graph", {"handle": symbol.handle})
    registry.call("materialize_reference_graph", {"handle": reference.handle})

    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    assert conn.execute("SELECT count(*) FROM materialized_tables").fetchone() == (1,)
    assert conn.execute("SELECT symbol_name FROM materialized_symbols").fetchone() == ("f",)
    assert conn.execute("SELECT count(*) FROM materialized_references").fetchone() == (1,)
    conn.close()


def test_sync_materialize_uses_materializer_tool_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".dorje").mkdir()
    (tmp_path / ".dorje" / "materialize.yaml").write_text(
        """
materialize:
  extracted_markdown:
    - tool: materialize_markdown_section_chunks
      args:
        write_fts: true
""".strip(),
        encoding="utf-8",
    )
    HandleStore().put("# A\n\nAlpha\n\n## B\n\nBeta", content_type="text/markdown", derivative_type="extracted_markdown")

    result = sync_materialize(tmp_path)

    assert result.added == 1
    assert result.details["results"][0]["materializer"] == "materialize_markdown_section_chunks"
    assert result.details["results"][0]["chunks"] == 2
