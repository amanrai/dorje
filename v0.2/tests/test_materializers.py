from pathlib import Path

import orjson

from dorje.db import connect, init_schema
from dorje.handles import HandleStore
from dorje.materializers import load_materialize_config, materialize_corpus


def test_materialize_config_can_override_text_chunker(tmp_path: Path) -> None:
    (tmp_path / ".dorje").mkdir()
    (tmp_path / ".dorje" / "materialize.yaml").write_text(
        """
materialize:
  extracted_markdown:
    - materializer: text_chunks
      config:
        chunker: section
        write_fts: true
""".strip(),
        encoding="utf-8",
    )

    config = load_materialize_config(tmp_path)

    assert config["extracted_markdown"][0]["config"]["chunker"] == "section"


def test_materialize_corpus_routes_text_and_structured_derivatives(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = HandleStore(tmp_path / ".dorje" / "handles")
    store.put("# A\n\nAlpha\n\n## B\n\nBeta", content_type="text/markdown", derivative_type="extracted_markdown", label="doc.md")
    store.put(
        orjson.dumps({"schema": "dorje.table.v1", "columns": [], "rows": []}).decode(),
        content_type="application/vnd.dorje.table+json",
        derivative_type="table",
        label="table",
    )

    result = materialize_corpus(tmp_path, max_chars=100)

    assert result["counts"]["text_chunks"] == 1
    assert result["counts"]["fts_rows"] == 1
    assert result["counts"]["structured_artifacts"] == 1
    conn = connect(tmp_path / ".dorje" / "dorje.sqlite")
    init_schema(conn)
    assert conn.execute("SELECT count(*) FROM chunks").fetchone() == (1,)
    assert conn.execute("SELECT count(*) FROM chunks_fts").fetchone() == (1,)
    assert conn.execute("SELECT count(*) FROM materialized_artifacts").fetchone() == (1,)
    conn.close()
