import base64
import orjson
from pathlib import Path
from typing import Any, cast

import pytest

from dorje.extensions import load_extensions
from dorje.handles import HandleStore


def _registry():
    root = Path(__file__).resolve().parents[1] / "base_extensions"
    return load_extensions(roots=(root,))


def test_extract_html_to_markdown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "a.html"
    path.write_text("<h1>A</h1><script>bad()</script><p>Body</p>", encoding="utf-8")
    source = HandleStore().put_file_ref(path, "text/html", label="a.html")

    result = cast(dict[str, Any], _registry().call("extract_html_to_markdown", {"handle": source.handle}))

    assert result["derivative_type"] == "extracted_markdown"
    output = HandleStore().get(cast(str, result["handle"]))
    assert "# A" in output.content
    assert "Body" in output.content
    assert "bad()" not in output.content
    assert output.metadata["derived_from"] == source.handle


def test_extract_html_tables_and_figures_emit_normalized_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    html = tmp_path / "a.html"
    html.write_text(
        '<table><caption>Cap</caption><tr><td>A</td></tr></table><figure><img src="img.png" alt="Alt"><figcaption>Fig cap</figcaption></figure>',
        encoding="utf-8",
    )
    source = HandleStore().put_file_ref(html, "text/html", label="a.html")
    registry = _registry()

    tables = cast(dict[str, Any], registry.call("extract_tables_from_html", {"handle": source.handle}))
    figures = cast(dict[str, Any], registry.call("extract_figures_from_html", {"handle": source.handle}))

    table_collection = HandleStore().get(cast(str, tables["handle"]))
    table = HandleStore().get(cast(str, table_collection.members[0]["handle"]))
    table_payload = orjson.loads(table.content)
    assert table.content_type == "application/vnd.dorje.table+json"
    assert table.derivative_type == "table"
    assert table_payload["caption"] == "Cap"
    assert "markdown" in table_payload

    figure_collection = HandleStore().get(cast(str, figures["handle"]))
    figure = HandleStore().get(cast(str, figure_collection.members[0]["handle"]))
    figure_payload = orjson.loads(figure.content)
    assert figure.content_type == "application/vnd.dorje.figure+json"
    assert figure.derivative_type == "figure"
    assert figure_payload["caption"] == "Fig cap"
    assert figure_payload["alt"] == "Alt"


def test_get_images_for_html_fetches_local_images_as_base64(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    image_bytes = b"fake-png"
    (tmp_path / "img.png").write_bytes(image_bytes)
    html = tmp_path / "a.html"
    html.write_text('<figure><img src="img.png" alt="Alt"></figure>', encoding="utf-8")
    source = HandleStore().put_file_ref(html, "text/html", label="a.html")

    result = cast(dict[str, Any], _registry().call("get_images_for_html", {"handle": source.handle}))

    assert result["derivative_type"] == "image_collection"
    assert result["members_count"] == 1
    collection = HandleStore().get(cast(str, result["handle"]))
    image = HandleStore().get(cast(str, collection.members[0]["handle"]))
    payload = orjson.loads(image.content)
    assert payload["base64"] == base64.b64encode(image_bytes).decode("ascii")
    assert payload["media_type"] == "image/png"
    assert image.derivative_type == "image"


def test_extract_plaintext_to_markdown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    source = HandleStore().put_file_ref(path, "text/plain", label="a.txt")

    result = cast(dict[str, Any], _registry().call("extract_plaintext_to_markdown", {"handle": source.handle}))

    output = HandleStore().get(cast(str, result["handle"]))
    assert output.content == "hello\n"
    assert output.content_type == "text/markdown"


def test_extract_references_emit_normalized_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "paper.md"
    path.write_text("# Paper\n\n## References\n\n- First ref\n- Second ref\n", encoding="utf-8")
    source = HandleStore().put_file_ref(path, "text/markdown", label="paper.md")

    result = cast(dict[str, Any], _registry().call("extract_references_from_paper", {"handle": source.handle}))

    collection = HandleStore().get(cast(str, result["handle"]))
    reference = HandleStore().get(cast(str, collection.members[0]["handle"]))
    payload = orjson.loads(reference.content)
    assert reference.content_type == "application/vnd.dorje.reference+json"
    assert reference.derivative_type == "reference"
    assert payload["text"] == "- First ref\n"


def test_pdf_extractors_are_registered_placeholders(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4\n")
    source = HandleStore().put_file_ref(path, "application/pdf", label="paper.pdf")
    registry = _registry()

    for tool_name in ("extract_pdf_to_markdown", "extract_images_from_pdf", "extract_figures_from_pdf", "extract_tables_from_pdf"):
        with pytest.raises(NotImplementedError, match="not installed yet"):
            registry.call(tool_name, {"handle": source.handle})


def test_extract_python_symbols(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "mod.py"
    path.write_text("class A:\n    pass\n\ndef f():\n    return 1\n", encoding="utf-8")
    source = HandleStore().put_file_ref(path, "text/x-code-python", label="mod.py")

    result = cast(dict[str, Any], _registry().call("extract_python_symbols", {"handle": source.handle}))

    assert result["derivative_type"] == "code_symbol_collection"
    assert result["members_count"] == 2
    collection = HandleStore().get(cast(str, result["handle"]))
    names = {member["metadata"]["symbol_name"] for member in collection.members}
    assert names == {"A", "f"}
